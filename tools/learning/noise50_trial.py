"""Opt-in, zero-update 50 ms exploration / passive-yaw diagnostic adapters."""
from copy import deepcopy
import numpy as np
from tools.control.fixed_admittance import FixedAdmittance
from tools.control.yaw_admittance import YawFixedAdmittance
from tools.learning.persistent_exploration import HeldExploration
from tools.learning.five_axis_contract import field_slices, permission

VERSION = 'noise50_passive_yaw_diagnostic_v1'


def behavior_contract(passive_yaw_enabled):
    if type(passive_yaw_enabled) is not bool:
        raise ValueError('Explicit yaw-channel Boolean required')
    return dict(version=VERSION, noise_hold_cycles=25, control_period_s=.002,
        noise_clock='absolute_control_cycle_common_seed_tape',
        passive_yaw_enabled=passive_yaw_enabled, optimizer_updates=0,
        replay_publication=False, policy_parameters_update_period_s=.002,
        reward_or_entropy_changed=False, new_observation_history=False)


class YawOnlyOff(YawFixedAdmittance):
    """Keep original four-axis feedback; never integrate a hidden yaw state."""
    def command(self, wrench_M_world, dt):
        result = FixedAdmittance.command(self, wrench_M_world, dt)
        self.yaw_velocity = self.yaw_offset = 0.
        return result

    def metadata(self):
        return {**super().metadata(), 'passive_yaw_enabled': False,
                'name': 'four_axis_admittance_yaw_only_disabled_v1'}


def session_class(passive_yaw_enabled):
    from tools.learning.consistent_sac_trial import session_class as base_class
    from tools.learning.global_residual_session import make_controller
    Base = base_class()
    class DiagnosticSession(Base):
        def __init__(self, environment):
            super().__init__(environment)
            def factory():
                controller = make_controller(environment.profile)
                if not passive_yaw_enabled:
                    old = controller.admittance
                    controller.admittance = YawOnlyOff(old.config, yaw_config=old.yaw_config)
                return controller
            self.controller_factory = factory
            self.behavior_contract = behavior_contract(passive_yaw_enabled)
    return DiagnosticSession


class FrozenHeldPolicy:
    """No calls to trainer.action/update/publish; fresh mu/std every active cycle."""
    def __init__(self, trainer, seed):
        self.trainer = trainer
        self.sampler = HeldExploration(seed, hold_cycles=25)
        self.policy_calls = self.warmup_draws = 0
        self.last_log = {}; self.last_action = np.zeros(5)
        trainer.updater.policy.set_training_mode(False)

    def select(self, observation, *, cycle, phase, enabled):
        epsilon = self.sampler.noise_at(cycle, phase=phase, enabled=enabled)
        if enabled:
            if not permission(observation):
                raise ValueError('Source permission mismatch')
            import torch
            policy = self.trainer.updater.policy
            tensor, _ = policy.obs_to_tensor(np.asarray(observation, dtype=np.float32))
            self.policy_calls += 1
            with torch.no_grad():
                mean, log_std, _ = policy.actor.get_action_dist_params(tensor)
                noise = torch.as_tensor(epsilon, dtype=mean.dtype).reshape(1, 5)
                action = torch.tanh(mean + log_std.exp() * noise).cpu().numpy()[0]
            mu, sigma = mean.cpu().numpy()[0].tolist(), log_std.cpu().numpy()[0].tolist()
        else:
            action = np.zeros(5); mu = sigma = None
        self.last_action = np.asarray(action).copy()
        self.last_log = dict(noise=deepcopy(self.sampler.last_log), mean=mu,
                            log_std=sigma, policy_calls=self.policy_calls)
        return self.last_action.tolist()

    def finish_cycle(self, next_enabled):
        if not next_enabled:
            self.sampler._clear()  # Clear immediately, without advancing the absolute tape.


class HeldSourceReplay:
    """Adapt the original full auditor to independently replay all-cycle held noise."""
    def __init__(self, provider, contexts):
        self.provider, self.contexts, self.cursor = provider, contexts, 0

    @property
    def policy_calls(self): return self.provider.policy_calls

    @property
    def warmup_draws(self): return 0

    def _step(self, context, observation):
        action = self.provider.select(observation, cycle=context['cycle'],
                    phase=context['phase'], enabled=context['enabled'])
        if self.provider.last_log != context['source_log']:
            raise ValueError('Held-noise/parameter/counter source log differs')
        self.provider.finish_cycle(context['next_enabled'])
        self.cursor += 1
        return action

    def action(self, observation, *, deterministic=False, warmup=False):
        if deterministic or warmup:
            raise ValueError('Diagnostic source is stochastic frozen SAC')
        while self.cursor < len(self.contexts) and not self.contexts[self.cursor]['enabled']:
            self._step(self.contexts[self.cursor], None)
        if self.cursor >= len(self.contexts):
            raise ValueError('Unexpected source inference after end')
        return self._step(self.contexts[self.cursor], observation)

    def finish(self):
        while self.cursor < len(self.contexts):
            context = self.contexts[self.cursor]
            if context['enabled']: raise ValueError('Unreplayed active source row')
            self._step(context, None)
        return self.provider.sampler.state_dict()


def source_contexts(raw):
    spans = field_slices(); phases = ('INSERT','UNLOAD','SEARCH','WAIT_RECOVERY','FAILED')
    # Use the canonical observation vocabulary, not an assumed order.
    from tools.learning.observation import POLICY_PHASES
    result=[]
    for cycle,row in enumerate(raw['transitions']):
        phase = POLICY_PHASES[int(np.asarray(row['observation'])[spans['policy_phase']].argmax())]
        result.append(dict(cycle=cycle,phase=phase,enabled=row['action_active'],
            next_enabled=row['next_action_active'],source_log=row['action_log']['noise50']))
    return result


def verify_passive_channel(raw, enabled):
    """Check the logged channel against the exact world-Mz recurrence."""
    from tools.control.yaw_admittance import YawAdmittanceConfig
    import math
    c=YawAdmittanceConfig(); previous_updates=0; velocity=offset=0.; checked=0
    for index,state in enumerate(raw['trace']):
        yaw=state.get('yaw_admittance')
        if not yaw: continue
        if not enabled:
            if any(yaw[k] != 0 for k in ('velocity_rad_s','offset_rad','updates','limited_steps')):
                raise ValueError('Disabled yaw retained a hidden state')
        else:
            updates=yaw['updates']
            if updates < previous_updates or updates > previous_updates+1:
                raise ValueError('Yaw update clock discontinuity')
            if updates==previous_updates+1:
                before=raw['trace'][max(0,index-1)]
                mz=before['contact_wrench_M'][5]
                decay=math.exp(-c.damping*.002/c.virtual_inertia)
                proposed=decay*velocity+(1-decay)*mz/c.damping
                bounded=float(np.clip(proposed,-c.velocity_limit,c.velocity_limit))
                next_offset=float(np.clip(offset+bounded*.002,-c.correction_budget,c.correction_budget))
                velocity=(next_offset-offset)/.002;offset=next_offset;checked+=1
                if abs(yaw['velocity_rad_s']-velocity)>1e-12 or abs(yaw['offset_rad']-offset)>1e-12:
                    raise ValueError('Passive yaw recurrence differs')
            previous_updates=updates
    return dict(verified=True,passive_yaw_enabled=enabled,recurrence_updates_checked=checked)
