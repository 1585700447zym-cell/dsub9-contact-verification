"""Maximum-advance reward and one-time adjudicated terminal reward."""
import math


class EpisodeReward:
    def __init__(self, target_travel_m):
        if not math.isfinite(target_travel_m) or target_travel_m <= 0:
            raise ValueError('Positive finite target travel required')
        self.target = float(target_travel_m)
        self.maximum = 0.
        self.finalized = False

    def advance(self, *, advance_m, dt, force_N, torque_G_Nm):
        if self.finalized:
            raise RuntimeError('Reward already finalized')
        if not all(math.isfinite(x) for x in (advance_m, dt, force_N, torque_G_Nm)) or dt <= 0 or min(force_N, torque_G_Nm) < 0:
            raise ValueError('Finite progress, positive duration and nonnegative cycle loads required')
        maximum = max(self.maximum, min(self.target, max(0., advance_m)))
        parts = dict(progress=5*(maximum-self.maximum)/self.target,
                     time=-.1*dt, force=-.2*dt*(force_N/.025)**2,
                     torque=-.2*dt*(torque_G_Nm/.0005)**2)
        parts['total'] = sum(parts.values())
        self.maximum = maximum
        return parts

    def finalize(self, task_outcome):
        if self.finalized:
            raise RuntimeError('Terminal reward already finalized')
        values = {'FULL_SUCCESS': 10., 'CONTACT_GUARD': -10., 'MOTION_VIOLATION': -10.,
                  'TASK_FAILURE': -2., 'INVALID_SIMULATION': 0., 'STOP_NOT_QUALIFIED': 0.,
                  'EXTERNAL_TRUNCATION': 0.}
        value = values[task_outcome]
        self.finalized = True
        return value
