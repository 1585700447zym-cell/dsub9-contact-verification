"""Candidate four-axis residual integration sharing the existing B2 lifecycle.

No policy updates, no model-domain certification and no learning permission.
"""
from copy import deepcopy
import numpy as np
from .action import compose_command, normalized_action, DEFAULT_ACTION_SCALE, validated_action_scale
from .guarded_session import CandidateEpisodeSession
from .observation import ObservationBuilder
from .reward import EpisodeReward
from .episode_buffer import _safe_error_archive


class ResidualSession(CandidateEpisodeSession):
    def __init__(self, *, environment, controller_factory=None, action_scale=DEFAULT_ACTION_SCALE,
                 finish_criteria=None, geometry_checker=None):
        self._action_scale = validated_action_scale(action_scale)
        self._features_ready = False
        self._decorated_cache = None
        super().__init__(environment=environment, controller_factory=controller_factory,
                         finish_criteria=finish_criteria, geometry_checker=geometry_checker)

    def reset(self, case, seed=None):
        self.interface_fault = None
        try:
            return self._reset_residual(case, seed)
        except Exception as exc:
            self._abort_interface(exc)
            raise

    def _abort_interface(self, exc):
        # Close access BEFORE diagnostics, even when the cache is only half built.
        self._ready = self._features_ready = False
        self._cache = self._decorated_cache = None
        self.done = self.task_finished = True
        if self.interface_fault is None:
            self.interface_fault = _safe_error_archive(dict(error=repr(exc),
                controller=self.controller_state_snapshot() if hasattr(self, 'controller') else None))
        if self.env.guard_facts['simulation_valid']:
            if hasattr(self.env, 'command'):
                self.env._terminate('INVALID_INTERFACE_DATA')
            else:
                self.env._facts['simulation_valid'] = False
                self.env._facts['invalid_reasons'].append('INVALID_INTERFACE_DATA')
                self.env.phase = 'TERMINAL'

    def _reset_residual(self, case, seed):
        self._ready = False
        self._cache = None
        self.done = self.task_finished = True
        self._features_ready = False
        self._decorated_cache = None
        self.previous_residual = [0.]*4
        self.last_action_log = {}
        self.policy_raw = {}
        self.clipped_duration_s = 0.
        self.external_cut = False
        self.reward = EpisodeReward(case.target_depth_m)
        initial = super().reset(case, seed)
        self.observations = ObservationBuilder(initial.state, self.controller.config)
        self._features_ready = True
        return self.prepare_cycle()

    def start_external_tail(self):
        """Close interaction at a saved cutoff; audit independently, no task bonus."""
        if not self._ready or self.done:
            raise RuntimeError('Active episode required for external cut')
        self.external_cut = True
        if self.stop_time is None:
            self._finish('EXTERNAL_TRUNCATION')
        self.task_finished = True
        self.task_end_time = float(self.env.data.time)
        self._cache = None

    def _validate_action(self, action4):
        return normalized_action(action4)

    def _command_for_action(self, snapshot, action):
        command, log = compose_command(snapshot.base_command, action,
            phase=snapshot.controller_state['phase'], enabled=snapshot.residual_enabled,
            previous_limited=self.env.command.copy(), dt=self.env.config.control_period,
            action_scale=self._action_scale)
        self.last_action_log = log
        self.previous_residual = np.asarray(log['applied_residual'])[[0, 1, 3, 4]].tolist()
        return command

    def prepare_cycle(self):
        if not self._ready:
            raise RuntimeError('A successful reset is required')
        try:
            return self._prepare_residual()
        except Exception as exc:
            self._abort_interface(exc)
            raise

    def _prepare_residual(self):
        snapshot = super().prepare_cycle()
        if not self._features_ready:
            return snapshot
        if self._decorated_cache is not self._cache:
            from tools.validation.native313_matrix_audit import actual_stop_start
            context = dict(reason=self.reason, recovery_state=self.recovery_state,
                recovery_count=self.env.recovery_count, hold_start=self.hold_start,
                wait_start=self.wait_start, actual_stop_start=actual_stop_start(self.env.events, self.stop_time),
                previous_residual=self.previous_residual, guard_facts=self.env.guard_facts)
            # stop/resume resets the live drive reference after the frozen sensor
            # sample. Update only policy input, never that archived physical trace.
            policy_snapshot = deepcopy(snapshot)
            policy_snapshot.state['reference_qpos'] = self.env.reference.tolist()
            vector, raw = self.observations.capture(policy_snapshot, context, refresh=True)
            self.policy_raw = raw
            self._cache.policy_observation = vector.tolist()
            self._cache.policy_raw = deepcopy(raw)
            self._cache.privileged_evaluation = dict(case_name=self.case.name,
                position_m=list(snapshot.state['position_m']),
                quaternion_wxyz=list(snapshot.state['quaternion_wxyz']),
                penetration_m=snapshot.state['penetration_m'], contact_count=snapshot.state['contact_count'])
            self._decorated_cache = self._cache
        return deepcopy(self._cache)

    def advance_cycle(self, action4):
        if not self._ready or self.done:
            raise RuntimeError('Successful reset and active episode required')
        try:
            return self._advance_residual(action4)
        except Exception as exc:
            self._abort_interface(exc)
            raise

    def _advance_residual(self, action4):
        result = super().advance_cycle(action4)
        row = result.trace_row
        parts = self.reward.advance(advance_m=row['position_m'][2]-self.initial[2],
                                   dt=result.dt, force_N=result.cycle_peaks['force_N'],
                                   torque_G_Nm=result.cycle_peaks['torque_G_Nm'])
        terminal = 0.
        if result.done:
            terminal = self.reward.finalize('EXTERNAL_TRUNCATION' if self.external_cut else result.outcome['task_outcome'])
        parts['terminal'] = terminal
        parts['total'] += terminal
        result.reward_terms = parts
        clipped = not np.allclose(self.last_action_log['effective_command_delta'],
                                 self.last_action_log['applied_residual'], rtol=0, atol=1e-15)
        self.clipped_duration_s = self.clipped_duration_s + result.dt if clipped else 0.
        self.last_action_log.update(actual_end_limited_command=list(result.executed_command),
                                    continuously_clipped_s=self.clipped_duration_s)
        result.action_log = deepcopy(self.last_action_log)
        return result
