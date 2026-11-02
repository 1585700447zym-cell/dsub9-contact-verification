"""Expose actuator-owned reference state in the same sensed relative frame."""
import numpy as np
from tools.learning.axis_session import AxisSearchSession
from tools.control.reference_search import DriveObservation


class ReferenceSearchSession(AxisSearchSession):
    def policy_observation(self,row):
        base=super().policy_observation(row)
        return DriveObservation(base.time_s,base.displacement_m,base.wrench_M,base.relative_rotation_rad,
            tuple(np.asarray(self.env.reference[:3])-self.initial),tuple(self.env.command[:2]))
