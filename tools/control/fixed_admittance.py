"""Fixed four-axis admittance using contact wrench at M in world axes.

No true hole error, search, recovery, learned parameters, or pose teleportation.
Integrated correction budgets constrain commanded corrections, not rigid-body
motion; the independent dynamic guard remains responsible for actual motion.
"""
from dataclasses import dataclass, asdict
import math
import numpy as np


@dataclass(frozen=True)
class AdmittanceConfig:
    virtual_mass: tuple = (.2,.2,.0002,.0002)
    damping: tuple = (20.,20.,.01,.01)
    velocity_limit: tuple = (.0005,.0005,.02,.02)
    correction_budget: tuple = (.0005,.0005,.08,.08)
    z_speed: float = .001

    def __post_init__(self):
        for name in ('virtual_mass','damping','velocity_limit','correction_budget'):
            value=np.asarray(getattr(self,name),dtype=float)
            if value.shape!=(4,) or not np.isfinite(value).all() or np.any(value<=0):
                raise ValueError(name+' must contain four finite positive values')
        if not math.isfinite(self.z_speed) or self.z_speed<=0:
            raise ValueError('z_speed must be finite and positive')


class FixedAdmittance:
    def __init__(self,config=None,*,feedback_enabled=True):
        self.config=config or AdmittanceConfig()
        self.feedback_enabled=bool(feedback_enabled)
        self.reset()

    def reset(self):
        self.velocity=np.zeros(4);self.offset=np.zeros(4);self.limited_steps=0

    def command(self,wrench_M_world,dt):
        w=np.asarray(wrench_M_world,dtype=float)
        if w.shape!=(6,) or not np.isfinite(w).all() or not math.isfinite(dt) or dt<=0:
            raise ValueError('Finite six-axis wrench and positive dt required')
        if not self.feedback_enabled:return np.array([0,0,self.config.z_speed,0,0,0])
        mass=np.asarray(self.config.virtual_mass);damping=np.asarray(self.config.damping)
        decay=np.exp(-damping*dt/mass)
        proposed=decay*self.velocity+(1-decay)*w[[0,1,3,4]]/damping
        bounded=np.clip(proposed,-np.asarray(self.config.velocity_limit),self.config.velocity_limit)
        next_offset=np.clip(self.offset+bounded*dt,-np.asarray(self.config.correction_budget),self.config.correction_budget)
        applied=(next_offset-self.offset)/dt
        if not np.allclose(proposed,applied,rtol=0,atol=1e-14):self.limited_steps+=1
        self.velocity=applied;self.offset=next_offset
        return np.array([applied[0],applied[1],self.config.z_speed,applied[2],applied[3],0.])

    def metadata(self):
        return {'name':'B1_fixed_admittance' if self.feedback_enabled else 'zero_feedback_reference',
                'config':asdict(self.config),'equation':'M dv/dt + D v = [Fx,Fy,Tx,Ty]',
                'wrench_reference':'M','axes':'world/task','learned':False,
                'search_or_recovery':False,'budget_type':'integrated_commanded_correction'}
