"""Load-warning experiment with increased SEARCH-only XY residual authority."""
from dataclasses import replace

from . import load_warning_trial as previous
from .load_warning_trial import OBSERVATION_VERSION, receipt_fields

VERSION = 'nano100_yaw_on_load_warning_900_search_authority_v2'
XY_RESIDUAL_M_S = .00075
XY_ACCELERATION_M_S2 = .020


def protocol_config(search_speed_um_s=900):
    contract = previous.protocol_config(search_speed_um_s)
    contract.update(version=VERSION, search_authority=dict(
        search_xy_residual_m_s=XY_RESIDUAL_M_S, search_xy_acceleration_m_s2=XY_ACCELERATION_M_S2))
    contract['search_drive_config']['linear_acceleration_m_s2'] = XY_ACCELERATION_M_S2
    return contract


def environment_class():
    class SearchAuthorityEnvironment(previous.environment_class()):
        search_authority_version = VERSION

        def step(self, command):
            if self.phase != 'RUNNING' or self.search_reference_center is None:
                return super().step(command)
            limits = self.acceleration_limits
            self.acceleration_limits = limits.copy()
            self.acceleration_limits[:2] = XY_ACCELERATION_M_S2
            try:
                return super().step(command)
            finally:
                self.acceleration_limits = limits

    return SearchAuthorityEnvironment


def session_class(search_speed_um_s=900):
    class SearchAuthoritySession(previous.session_class(search_speed_um_s)):
        def __init__(self, environment):
            if getattr(environment, 'search_authority_version', None) != VERSION:
                raise TypeError('Registered SEARCH authority environment required')
            super().__init__(environment)
            self.contract = protocol_config(search_speed_um_s)
            self.controller_factory = self._make_search_authority_controller

        def _make_search_authority_controller(self):
            controller = previous.make_controller(self.env.profile, search_speed_um_s=search_speed_um_s)
            controller.drive_config = replace(controller.drive_config, linear_acceleration_m_s2=XY_ACCELERATION_M_S2)
            return controller

    return SearchAuthoritySession
