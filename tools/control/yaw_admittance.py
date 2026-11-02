"""Opt-in M/world yaw admittance; retain the original four-axis state/API."""
from dataclasses import asdict, dataclass, replace
import math
import numpy as np

from tools.control.fixed_admittance import FixedAdmittance
from tools.control.reference_search import ReferenceSearchRecovery


@dataclass(frozen=True)
class YawAdmittanceConfig:
    virtual_inertia: float = .02
    damping: float = 1.
    velocity_limit: float = .02
    correction_budget: float = .08

    def __post_init__(self):
        if any(isinstance(v,bool) or not math.isfinite(v) or v<=0 for v in asdict(self).values()):
            raise ValueError('Yaw parameters must be finite positive values')


class YawFixedAdmittance(FixedAdmittance):
    def __init__(self,config=None,*,yaw_config=None,feedback_enabled=True):
        self.yaw_config=yaw_config or YawAdmittanceConfig()
        super().__init__(config,feedback_enabled=feedback_enabled)

    def reset(self):
        super().reset()
        self.yaw_velocity=self.yaw_offset=0.
        self.yaw_updates=self.yaw_limited_steps=0

    def command(self,wrench_M_world,dt):
        command=super().command(wrench_M_world,dt)
        if not self.feedback_enabled:
            return command
        c=self.yaw_config
        decay=math.exp(-c.damping*dt/c.virtual_inertia)
        proposed=decay*self.yaw_velocity+(1-decay)*float(wrench_M_world[5])/c.damping
        bounded=float(np.clip(proposed,-c.velocity_limit,c.velocity_limit))
        offset=float(np.clip(self.yaw_offset+bounded*dt,-c.correction_budget,c.correction_budget))
        applied=(offset-self.yaw_offset)/dt
        self.yaw_limited_steps+=int(not math.isclose(proposed,applied,rel_tol=0,abs_tol=1e-14))
        self.yaw_velocity=applied;self.yaw_offset=offset;self.yaw_updates+=1
        command[5]=applied
        return command

    def yaw_state(self):
        return dict(velocity_rad_s=self.yaw_velocity,offset_rad=self.yaw_offset,
                    updates=self.yaw_updates,limited_steps=self.yaw_limited_steps)

    def metadata(self):
        return {**super().metadata(),'name':'fixed_admittance_with_independent_yaw_v1',
                'yaw_admittance':asdict(self.yaw_config),'yaw_equation':'J dv/dt + D v = Mz',
                'yaw_reference':'M/world','active_yaw_scan':False}


class YawSearchRecovery(ReferenceSearchRecovery):
    def command(self,obs,dt):
        updates=self.admittance.yaw_updates
        result=super().command(obs,dt)
        # Legacy UNLOAD rebuilds its six-vector with yaw zero. Preserve the
        # angular update already made there, without integrating it twice.
        if self.phase=='UNLOAD' and self.admittance.yaw_updates==updates+1:
            result[5]=self.admittance.yaw_velocity
        return result


def make_yaw_controller(profile=None):
    from tools.learning.newton_profile import make_controller
    from tools.learning.newton_damping import NewtonProfile
    p=profile or NewtonProfile()
    old=make_controller(p)
    config=replace(old.config,spiral_radius_m=.0004,spiral_pitch_m=.0001,
                   spiral_speed_m_s=.00045,search_time_s=18.,search_actual_xy_limit_m=.0006,
                   search_xy_component_speed_m_s=.00045,total_action_time_s=25.)
    controller=YawSearchRecovery(config,old.risk_config,old.load_config,old.drive_config)
    controller.admittance=YawFixedAdmittance(old.admittance.config)
    return controller
