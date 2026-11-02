"""Independent 30-second residual interface; old controllers and archives are untouched."""
from dataclasses import replace
import numpy as np
from .global_residual_action import compose_command, profile_config, ReferenceEnvelopeInfeasible


def make_controller(profile=None):
    from tools.control.yaw_admittance import make_yaw_controller
    controller = make_yaw_controller(profile)
    controller.config = replace(controller.config, total_action_time_s=30.)
    return controller


def session_class(profile):
    contract = profile_config(profile)
    from .five_axis_session import session_class as original_class
    Base = original_class()

    class GlobalResidualSession(Base):
        def __init__(self, environment):
            super().__init__(environment)
            self.profile_id = profile
            self.contract = profile_config(profile)
            self._action_scale = tuple(contract['action_scale'])
            self.controller_factory = lambda: make_controller(self.env.profile)

        def _reset_residual(self, case, seed):
            snapshot = super()._reset_residual(case, seed)
            self.observations.version = contract['observation_version']
            return snapshot

        def _command_for_action(self, snapshot, action):
            from .layered_session import LayeredReferenceSession
            # Preserve the original one-shot reference release and XY rebase.
            base = LayeredReferenceSession._command_for_action(self, snapshot, action)
            phase = snapshot.controller_state['phase']; reference = None
            if phase == 'SEARCH' and snapshot.residual_enabled:
                reference = (self.env.reference[:3] - self.initial - self.controller.search_origin)[:2]
            try:
                command, log = compose_command(base, action, profile=self.profile_id, phase=phase, enabled=snapshot.residual_enabled,
                    previous_limited=self.env.command.copy(), dt=self.env.config.control_period,
                    reference_xy=reference, radius=self.controller.config.spiral_radius_m)
            except ReferenceEnvelopeInfeasible:
                reason = 'RESIDUAL_REFERENCE_INFEASIBLE'
                self.controller._fail(self.policy_observation(self.env.observe()), reason)
                self._finish(reason)
                command, log = compose_command([0.] * 6, action, profile=self.profile_id, phase='FAILED', enabled=False,
                    previous_limited=self.env.command.copy(), dt=self.env.config.control_period)
                log['reference_failure'] = reason
            self.last_action_log = log
            self.previous_residual = np.asarray(log['applied_residual'])[[0, 1, 3, 4, 5]].tolist()
            return command

    return GlobalResidualSession
