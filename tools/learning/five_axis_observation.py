"""Legacy four-sample history plus three necessary yaw-state fields, N2 scale."""
from copy import deepcopy
import numpy as np
from .v4_observation import V4ObservationBuilder
from .five_axis_contract import OBSERVATION_VERSION, field_slices, permission


class FiveAxisObservation(V4ObservationBuilder):
    version = OBSERVATION_VERSION

    def __init__(self, initial_state, config, profile):
        super().__init__(initial_state, config)
        self.profile = profile

    def capture(self, snapshot, context, *, refresh=False):
        previous = np.asarray(context['previous_residual'], dtype=float)
        if previous.shape != (5,) or not np.isfinite(previous).all():
            raise ValueError('Five-axis previous physical residual required')
        legacy = dict(context, previous_residual=previous[:4].tolist())
        vector, raw = super().capture(snapshot, legacy, refresh=refresh)
        scale = ([self.profile.force_guard_N] * 3 + [self.profile.torque_guard_Nm] * 3) * 4
        vector[self.slices['wrench_history_M']] = np.clip(np.asarray(raw['wrench_history_M']) / scale, -10, 10)
        self.schema[0]['scale'] = scale
        yaw = snapshot.controller_state['yaw_admittance']
        added = [('previous_yaw_residual', previous[4], .03, 'rad/s'),
                 ('yaw_admittance_velocity', yaw['velocity_rad_s'], .03, 'rad/s'),
                 ('yaw_admittance_offset', yaw['offset_rad'], .08, 'rad')]
        values = vector.tolist()
        for name, value, scale, unit in added:
            if not np.isfinite(value):
                raise ValueError('Finite yaw observation required')
            start = len(values); values.append(float(np.clip(value / scale, -10, 10)))
            raw[name] = [float(value)]; self.slices[name] = slice(start, start + 1)
            self.schema.append(dict(name=name, start=start, width=1, scale=[scale], unit=unit,
                source='previous_physical_residual_or_yaw_admittance'))
        if self.slices != field_slices():
            raise ValueError('Five-axis observation schema drift')
        result = np.asarray(values, dtype=np.float32)
        permission(result)
        return result, deepcopy(raw)
