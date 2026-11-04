"""Explicit 30-second G0/G1 entry with jointly bounded SEARCH references."""
from copy import deepcopy
import numpy as np
from tools.dynamics.reference_envelope import VERSION, ReferenceEnvelopeMixin, ReferenceIntersectionEmpty, constrain_xy
from tools.dynamics.safety import limit_command


def environment_class():
    # Keep runtime/environment imports lazy, as in the existing qualified entry.
    from tools.validation.yaw_pilot import environment_class as old_environment
    Base = old_environment()

    class ConsistentReferenceEnvironment(ReferenceEnvelopeMixin, Base):
        pass
    return ConsistentReferenceEnvironment


def session_class(profile='G1', *, search_xy_limit_m_s=.00045):
    from .global_residual_session import session_class as old_session
    Base = old_session(profile, search_xy_limit_m_s=search_xy_limit_m_s)

    class ConsistentReferenceSession(Base):
        def __init__(self, environment):
            if getattr(environment, 'reference_consistency_version', None) != VERSION:
                raise TypeError('The consistent-reference environment is required')
            super().__init__(environment)
            self.contract = deepcopy(self.contract)
            self.contract['version'] = f'global_residual_{profile}_30s_reference_consistent_v1'
            self.contract['reference_consistency_version'] = VERSION

        def _command_for_action(self, snapshot, action):
            command = super()._command_for_action(snapshot, action)
            e, c = self.env, self.controller
            active = c.phase == 'SEARCH' and e.phase == 'RUNNING' and self.reason is None
            center = (self.initial+c.search_origin)[:2] if active else None
            e.configure_search_envelope(center, c.config.spiral_radius_m if active else None)
            self.last_action_log.update(reference_consistency_version=VERSION, contract_version=self.contract['version'])
            if active:
                limited = limit_command(command, e.command, e.config.control_period,
                    [.001]*3+[.03]*3, [.005]*3+[.3]*3)
                desired = e.reference[:2]+limited[:2]*e.config.control_period
                # This uses the same geometry rule, with actual pose held fixed
                # for prediction. Live substeps use their own current actual pose.
                try:
                    predicted = constrain_xy(desired, e.data.qpos[:2], center,
                                             c.config.spiral_radius_m, e.config.reference_lead_m)
                except ReferenceIntersectionEmpty:
                    # The armed pre-PD hook requests the existing physical stop;
                    # _post_task_cycle then chooses recovery or budget exhaustion.
                    self.last_action_log['predicted_bounded_reference_xy_m'] = None
                    self.last_action_log['bounded_prediction_infeasible'] = True
                else:
                    self.last_action_log['predicted_bounded_reference_xy_m'] = (predicted-center).tolist()
                    self.last_action_log['bounded_prediction_infeasible'] = False
                self.last_action_log['bounded_prediction_assumes_fixed_actual'] = True
            return command

        def _post_task_cycle(self, row):
            e, c = self.env, self.controller
            if e.reference_failure_pending:
                e.reference_failure_pending = False
                obs = self.policy_observation(row)
                if not c.search_count_exhausted():
                    c._transition('WAIT_RECOVERY', obs, 'SEARCH_EXHAUSTED')
                    self.recovery_state, self.wait_start = 'WAIT_STOP', row['time_s']
                else:
                    c._fail(obs, 'SEARCH_BUDGET_EXHAUSTED')
                    self._finish('SEARCH_BUDGET_EXHAUSTED')
                c.events[-1]['reference_intersection_infeasible'] = True
            return super()._post_task_cycle(row)

        def _trace_row(self, row):
            result = super()._trace_row(row)
            state = getattr(self.env, 'reference_envelope_state', None)
            if state is not None:
                result['reference_consistency'] = state()
            return result

    return ConsistentReferenceSession
