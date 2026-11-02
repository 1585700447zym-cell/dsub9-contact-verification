"""Lazy five-axis residual adapter for the existing yaw/N2 episode lifecycle."""
from copy import deepcopy
import numpy as np
from .five_axis_action import normalized_action, compose_command, ReferenceEnvelopeInfeasible
from .five_axis_contract import SCALE


def session_class():
    from .residual_session import ResidualSession
    from .layered_session import LayeredReferenceSession
    from .session import EpisodeSession
    from .newton_profile import NewtonReward
    from .five_axis_observation import FiveAxisObservation
    from tools.validation.yaw_pilot import session_class as baseline_class
    Baseline = baseline_class()

    class FiveAxisResidualSession(ResidualSession, Baseline):
        def __init__(self, environment):
            if environment.profile.metadata()['id'] != 'newton_force_N2_damped_v1':
                raise ValueError('Current N2 force/drive profile required')
            expected = dict(control_period=.002, linear_speed=.001, angular_speed=.03,
                            linear_acceleration=.005, angular_acceleration=.3)
            if any(getattr(environment.config, key) != value for key, value in expected.items()):
                raise ValueError('Qualified common drive settings required')
            self._features_ready = False; self._decorated_cache = None
            self._action_scale = SCALE
            Baseline.__init__(self, environment)

        def _reset_residual(self, case, seed):
            self._ready = self._features_ready = False
            self._cache = self._decorated_cache = None
            self.done = self.task_finished = True
            self.previous_residual = [0.] * 5
            self.last_action_log = {}; self.policy_raw = {}
            self.clipped_duration_s = 0.; self.external_cut = False
            self.reward = NewtonReward(case.target_depth_m, self.env.profile)
            initial = Baseline.reset(self, case, seed)
            self.observations = FiveAxisObservation(initial.state, self.controller.config, self.env.profile)
            self._features_ready = True
            return self.prepare_cycle()

        def _validate_action(self, action):
            return normalized_action(action)

        def _prepare_residual(self):
            snapshot = Baseline.prepare_cycle(self)
            if not self._features_ready:
                return snapshot
            if self._decorated_cache is not self._cache:
                from tools.validation.native313_matrix_audit import actual_stop_start
                context = dict(reason=self.reason, recovery_state=self.recovery_state,
                    recovery_count=self.env.recovery_count, hold_start=self.hold_start,
                    wait_start=self.wait_start, actual_stop_start=actual_stop_start(self.env.events, self.stop_time),
                    previous_residual=self.previous_residual, guard_facts=self.env.guard_facts,
                    previous_filter_fraction=self.last_action_log.get('reference_filter_fraction', 1.))
                policy_snapshot = deepcopy(snapshot)
                policy_snapshot.state['reference_qpos'] = self.env.reference.tolist()
                policy_snapshot.state['limited_command_world'] = self.env.command.tolist()
                vector, raw = self.observations.capture(policy_snapshot, context, refresh=True)
                self.policy_raw = raw
                self._cache.policy_observation = vector.tolist(); self._cache.policy_raw = deepcopy(raw)
                self._cache.privileged_evaluation = dict(case_name=self.case.name,
                    position_m=list(snapshot.state['position_m']),
                    quaternion_wxyz=list(snapshot.state['quaternion_wxyz']),
                    penetration_m=snapshot.state['penetration_m'], contact_count=snapshot.state['contact_count'])
                self._decorated_cache = self._cache
            return deepcopy(self._cache)

        def _command_for_action(self, snapshot, action):
            # Preserve the original one-shot reference release and XY rebase.
            base = LayeredReferenceSession._command_for_action(self, snapshot, action)
            phase = snapshot.controller_state['phase']; reference = None
            if phase == 'SEARCH' and snapshot.residual_enabled:
                reference = (self.env.reference[:3] - self.initial - self.controller.search_origin)[:2]
            try:
                command, log = compose_command(base, action, phase=phase, enabled=snapshot.residual_enabled,
                    previous_limited=self.env.command.copy(), dt=self.env.config.control_period,
                    reference_xy=reference, radius=self.controller.config.spiral_radius_m)
            except ReferenceEnvelopeInfeasible:
                reason = 'RESIDUAL_REFERENCE_INFEASIBLE'
                self.controller._fail(self.policy_observation(self.env.observe()), reason)
                self._finish(reason)
                command, log = compose_command([0.] * 6, action, phase='FAILED', enabled=False,
                    previous_limited=self.env.command.copy(), dt=self.env.config.control_period)
                log['reference_failure'] = reason
            self.last_action_log = log
            self.previous_residual = np.asarray(log['applied_residual'])[[0, 1, 3, 4, 5]].tolist()
            return command

        def _advance_residual(self, action):
            # CandidateEpisodeSession.advance_cycle contains a legacy 4D guard.
            # Use the shared lifecycle with our 5D validator, then retain its
            # independent adjudication and the existing residual reward logic.
            result = EpisodeSession.advance_cycle(self, action)
            result.outcome = self.adjudicate()
            row = result.trace_row
            parts = self.reward.advance(advance_m=row['position_m'][2] - self.initial[2],
                dt=result.dt, force_N=result.cycle_peaks['force_N'],
                torque_G_Nm=result.cycle_peaks['torque_G_Nm'])
            terminal = self.reward.finalize('EXTERNAL_TRUNCATION' if self.external_cut
                else result.outcome['task_outcome']) if result.done else 0.
            parts['terminal'] = terminal; parts['total'] += terminal; result.reward_terms = parts
            clipped = not np.allclose(self.last_action_log['effective_command_delta'],
                                      self.last_action_log['applied_residual'], rtol=0, atol=1e-15)
            self.clipped_duration_s = self.clipped_duration_s + result.dt if clipped else 0.
            self.last_action_log.update(actual_end_limited_command=list(result.executed_command),
                continuously_clipped_s=self.clipped_duration_s)
            result.action_log = deepcopy(self.last_action_log)
            return result

    return FiveAxisResidualSession
