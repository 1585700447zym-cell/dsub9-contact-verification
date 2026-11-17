"""Fixed-checkpoint, all-cycle action sources for five-axis recovery experiments."""
from copy import deepcopy
from hashlib import sha256

import numpy as np
import torch

from tools.publication.five_axis_policy import tensor_digest
from .five_axis_collection import CollectionError, collect_episode as collect_cycles
from .five_axis_contract import field_slices, permission
from .observation import POLICY_PHASES
from .persistent_exploration import HeldExploration


VERSION = 'five_axis_cycle_policy_capture_v1'
_PHASE = field_slices()['policy_phase']


class CyclePolicy:
    """One frozen behavior actor. Each new episode starts its own memory and epsilon clock."""

    def __init__(self, policy_mode, actor, *, checkpoint_id, exploration_seed, deterministic=False):
        if policy_mode not in ('gru', 'mlp') or type(deterministic) is not bool:
            raise ValueError('Expected mlp or gru with an explicit Boolean evaluation mode')
        if not isinstance(checkpoint_id, str) or not checkpoint_id.strip():
            raise ValueError('Checkpoint identity required')
        if type(exploration_seed) is not int or exploration_seed < 0:
            raise ValueError('Nonnegative exploration seed required')
        methods = ('encode_step', 'distribution') if policy_mode == 'gru' else ('get_action_dist_params',)
        if not isinstance(actor, torch.nn.Module) or not all(callable(getattr(actor, m, None)) for m in methods):
            raise ValueError('Actor incompatible with policy_mode')
        memo = {}
        if policy_mode == 'mlp' and getattr(actor, 'action_dist', None) is not None:
            # SB3's last sampled distribution may hold the learner's autograd graph.
            # Collection needs only fresh mean/std, and must not mutate the live actor.
            from stable_baselines3.common.distributions import SquashedDiagGaussianDistribution
            dist = actor.action_dist
            if not isinstance(dist, SquashedDiagGaussianDistribution):
                raise ValueError('Registered squashed diagonal Gaussian actor required')
            memo[id(dist)] = SquashedDiagGaussianDistribution(dist.action_dim, epsilon=dist.epsilon)
        self._actor = deepcopy(actor, memo).cpu().eval().requires_grad_(False)
        self._source = dict(policy_mode=policy_mode, checkpoint_id=checkpoint_id,
                            actor_sha256=tensor_digest(self._actor.state_dict()),
                            exploration_seed=exploration_seed, deterministic=deterministic,
                            hold_cycles=25, period_s=.002)
        self._active = False
        self._episode_id = None

    @property
    def policy_mode(self):
        return self._source['policy_mode']

    @property
    def source(self):
        return dict(self._source, episode_id=self._episode_id)

    def begin_episode(self, episode_id):
        if self._active:
            raise RuntimeError('Finish the current episode before resetting memory')
        if not isinstance(episode_id, str) or not episode_id.strip():
            raise ValueError('Nonempty episode identity required')
        self._episode_id = episode_id
        self._noise = HeldExploration(self._source['exploration_seed'], hold_cycles=25)
        self._hidden = None
        self.records = []
        self._cycle_inputs = self._encoded_cycles = 0
        self._head_calls = 0
        self._active = True

    @property
    def counts(self):
        return dict(cycle_inputs=self._cycle_inputs, completed_cycle_inputs=len(self.records),
                    actor_head_calls=self._head_calls, encoded_cycles=self._encoded_cycles,
                    noise_refreshes=self._noise.draw_count)

    @torch.no_grad()
    def select_cycle(self, cycle_id, observation, enabled):
        if not self._active:
            raise RuntimeError('An active episode is required')
        if self._cycle_inputs != len(self.records):
            raise RuntimeError('An interrupted source cycle requires an episode reset')
        if type(cycle_id) is not int or cycle_id < 0:
            raise ValueError('Nonnegative integer cycle required')
        if type(enabled) not in (bool, np.bool_) or bool(enabled) != permission(observation):
            raise ValueError('Action source permission differs from observation')
        vector = np.asarray(observation, dtype='<f8')
        obs_hash = sha256(vector.tobytes()).hexdigest()
        if self.records and cycle_id == len(self.records)-1:
            previous = self.records[-1]
            if previous['observation_sha256'] != obs_hash or previous['enabled'] != bool(enabled):
                raise ValueError('Repeated cycle changed observation or permission')
            return previous['action'].copy()
        if cycle_id != len(self.records):
            raise ValueError('Policy cycles must be contiguous starting at zero')
        self._cycle_inputs += 1
        phase = POLICY_PHASES[int(vector[_PHASE].argmax())]
        epsilon = None
        if not self._source['deterministic']:
            epsilon = self._noise.noise_at(cycle_id, phase=phase, enabled=enabled)
        features = None
        if self.policy_mode == 'gru' or enabled:
            obs = torch.as_tensor(vector, dtype=torch.float32).unsqueeze(0)
        if self.policy_mode == 'gru':
            self._encoded_cycles += 1
            features, self._hidden = self._actor.encode_step(obs, self._hidden)
            if not torch.isfinite(self._hidden).all():
                raise ValueError('Nonfinite GRU hidden state')
        mean = log_std = None
        action = [0.] * 5
        if enabled:
            self._head_calls += 1
            if self.policy_mode == 'gru':
                mu, log_sigma = self._actor.distribution(features)
            else:
                mu, log_sigma, _ = self._actor.get_action_dist_params(obs)
            if (mu.shape != (1, 5) or log_sigma.shape != (1, 5)
                    or not torch.isfinite(mu).all() or not torch.isfinite(log_sigma).all()):
                raise ValueError('Finite five-axis Gaussian parameters required')
            sample = mu if epsilon is None else mu + log_sigma.exp() * mu.new_tensor(epsilon)
            if not torch.isfinite(sample).all():
                raise ValueError('Nonfinite policy sample')
            action = sample.tanh()[0].tolist()
            mean, log_std = mu[0].tolist(), log_sigma[0].tolist()
        self.records.append(dict(cycle_id=cycle_id, enabled=bool(enabled), phase=phase,
                                 observation_sha256=obs_hash, mean=mean, log_std=log_std,
                                 noise=deepcopy(self._noise.last_log) if epsilon is not None else None,
                                 action=action.copy()))
        return action

    def end_episode(self):
        if not self._active:
            raise RuntimeError('No active episode')
        self._hidden = None
        self._active = False


def collect_episode(session, case, *, provider, episode_id, seed=None, max_cycles=16000,
                    physical_protocol="recovery"):
    """Collect a quarantined episode under the registered protocol and stop-audit tail."""
    from . import time_budget_trial
    from .recovery_learning_contract import LOAD_WARNING_PROTOCOLS, SOURCE_ONLY, physical_projection, trial_module

    template = deepcopy(session.contract)
    trial = trial_module(physical_protocol)
    matched = [speed for speed, limit in time_budget_trial.SPEEDS.items()
               if template.get("search_xy_limit_m_s") == limit]
    if len(matched) != 1 or type(max_cycles) is not int or not 0 < max_cycles <= template['max_cycles']:
        raise ValueError('Registered physical session and cycle ceiling required')
    physical = physical_projection(template, matched[0], physical_protocol)
    base_time_protocol = {k: v for k, v in time_budget_trial.protocol_config(matched[0]).items()
                          if k not in SOURCE_ONLY}

    def bind(raw):
        raw.update(version=VERSION, episode_id=episode_id, policy_mode=provider.policy_mode,
                   policy_source=provider.source, source_cycles=provider.records,
                   source_counts=provider.counts, force_recovery_protocol=physical,
                   time_budget_protocol=base_time_protocol,
                   training_admitted=False, valid_for_learning=False)
        if not raw['cost']['initializations_completed']:
            return  # A failed reset may leave stale native evidence from the preceding episode.
        try:
            evidence = trial.receipt_fields(session)
        except Exception as exc:
            field = 'load_warnings' if physical_protocol in LOAD_WARNING_PROTOCOLS else 'force_recovery'
            if not raw.get('error'):
                kind = 'load warning' if physical_protocol in LOAD_WARNING_PROTOCOLS else 'recovery'
                raw['error'] = f'Failed to capture {kind} evidence: ' + repr(exc)
                raise CollectionError(raw['error'], raw) from exc
            raw['evidence']['diagnostic_errors'][field] = repr(exc)
            return
        raw.update(evidence)
        raw['evidence'].update(deepcopy(evidence))

    provider.begin_episode(episode_id)
    try:
        try:
            raw = collect_cycles(session, case, seed=seed, policy=None,
                                 cycle_policy=provider.select_cycle, max_cycles=max_cycles)
        except CollectionError as exc:
            bind(exc.archive)
            raise
        bind(raw)
        if raw.get('observation_version') != trial.OBSERVATION_VERSION or session.contract != template:
            raw['error'] = 'Recovery session contract or observation changed'
            raise CollectionError(raw['error'], raw)
        return raw
    finally:
        provider.end_episode()
