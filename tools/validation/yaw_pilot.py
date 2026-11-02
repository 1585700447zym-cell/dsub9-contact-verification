"""Four exact development poses; diagnostics never feed the controller."""
from dataclasses import dataclass, replace
import math
import xml.etree.ElementTree as ET
import numpy as np

from tools.validation.run_contact_cases import ContactCase, FORMAL_MODEL


@dataclass(frozen=True)
class YawContactCase(ContactCase):
    yaw_rad: float = 0.

    def __post_init__(self):
        values=(self.x_offset_m,self.y_offset_m,self.roll_rad,self.pitch_rad,self.yaw_rad,
                self.start_origin_z_m,self.target_depth_m)
        if any(isinstance(v,bool) or not math.isfinite(v) for v in values):
            raise ValueError('Finite initial pose required')


def pilot_cases():
    return [YawContactCase(name,.0003,.0003,math.radians(-1.),math.radians(1.),-.005,.005,
                           math.radians(angle))
            for name,angle in [('YAW_P10',1.),('YAW_M10',-1.),('YAW_P15',1.5),('YAW_M15',-1.5)]]


def rotation_matrix(q):
    q=np.asarray(q,dtype=float)
    if q.shape!=(4,) or not np.isfinite(q).all() or not np.any(q):
        raise ValueError('Finite nonzero quaternion required')
    q=q/np.max(np.abs(q));w,x,y,z=q/np.linalg.norm(q)
    return np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                     [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                     [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])


_pins=ET.parse(FORMAL_MODEL).getroot().findall('.//geom[@class="pin_collision"]')
_centers=np.array([[float(v) for v in g.get('pos').split()] for g in _pins])
_half=np.array([float(g.get('size').split()[1]) for g in _pins])


def pin_diagnostics(row):
    r=rotation_matrix(row['quaternion_wxyz']);p=np.asarray(row['position_m'])
    tips=(_centers+np.c_[np.zeros((9,2)),_half])@r.T+p
    bases=(_centers-np.c_[np.zeros((9,2)),_half])@r.T+p
    return [dict(pin=i+1,tip_world_m=tip.tolist(),base_world_m=base.tolist(),
                 tip_xy_offset_m=(tip[:2]-center[:2]).tolist(),
                 tip_past_entry_plane=bool(tip[2]>=0.))
            for i,(tip,base,center) in enumerate(zip(tips,bases,_centers))]


def environment_class():
    from tools.learning.newton_damping import environment_class as base_class
    Base=base_class()

    class YawEnvironment(Base):
        def __init__(self,profile=None):
            super().__init__(profile)
            self.guard_config=replace(self.guard_config,initial_roll_pitch_limit_rad=math.radians(1.5))

        def reset(self,case,*,allow_initial_contact=False):
            yaw=getattr(case,'yaw_rad',0.)
            if isinstance(yaw,bool) or not math.isfinite(yaw) or abs(yaw)>math.radians(1.5):
                self._observation_ready=False
                self.phase='TERMINAL'
                raise ValueError('Initial yaw outside pilot range')
            return super().reset(case,allow_initial_contact=allow_initial_contact)
    return YawEnvironment


def session_class():
    from tools.learning.layered_session import LayeredReferenceSession
    from tools.model.clearance_task import finish_criteria
    from tools.model.layered_task import layered_pin_fit
    from tools.control.yaw_admittance import make_yaw_controller

    class YawBaselineSession(LayeredReferenceSession):
        def __init__(self,environment):
            criteria={**finish_criteria(),'force_N':environment.profile.force_guard_N,
                      'torque_Nm':environment.profile.torque_guard_Nm}
            super().__init__(environment=environment,
                controller_factory=lambda:make_yaw_controller(environment.profile),
                finish_criteria=criteria,geometry_checker=layered_pin_fit)

        def controller_state_snapshot(self):
            state=super().controller_state_snapshot()
            state['yaw_admittance']=self.controller.admittance.yaw_state()
            return state

        def _trace_row(self,row):
            result=super()._trace_row(row)
            result['yaw_admittance']=self.controller.admittance.yaw_state()
            return result
    return YawBaselineSession
