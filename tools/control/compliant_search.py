"""Search tracks one bounded spiral-plus-admittance reference, in sensed coordinates."""
import math
import numpy as np
from tools.control.load_search import LoadSearchRecovery


def bounded_target(point,velocity,radius):
    """Disk projection and its directional derivative (outward at boundary)."""
    q=np.asarray(point,dtype=float);v=np.asarray(velocity,dtype=float)
    if q.shape!=(2,) or v.shape!=(2,) or not np.isfinite(np.r_[q,v,radius]).all() or radius<=0:
        raise ValueError('Finite XY target/velocity and positive radius required')
    norm=float(np.linalg.norm(q))
    if norm>radius:
        n=q/norm
        return n*radius,(radius/norm)*(v-n*np.dot(n,v))
    if norm==radius:
        n=q/norm
        return q.copy(),v-n*max(0.,np.dot(n,v))
    return q.copy(),v.copy()


class CompliantSearchRecovery(LoadSearchRecovery):
    def __init__(self,config=None,risk_config=None,load_config=None):
        super().__init__(config,risk_config,load_config)
        self.search_admittance_origin=None
        self.search_composition=None

    def _transition(self,phase,obs,reason):
        super()._transition(phase,obs,reason)
        if phase!='SEARCH':self.search_composition=None

    def _start_search(self,obs):
        self.search_admittance_origin=self.admittance.offset[:2].copy()
        self.search_composition=None
        super()._start_search(obs)
        self.events[-1]['admittance_origin_xy_m']=self.search_admittance_origin.tolist()

    def _search_command(self,obs,dt):
        if self.search_admittance_origin is None:
            raise RuntimeError('Search admittance origin required')
        c=self.config;w=np.asarray(obs.wrench_M);delta=np.asarray(obs.displacement_m)-self.search_origin
        correction=self.admittance.offset[:2]-self.search_admittance_origin
        base=self.admittance.command(w,dt)
        b=c.spiral_pitch_m/(2*math.pi);radius=b*self.theta
        rate=c.spiral_speed_m_s/math.hypot(radius,b)
        tangent=np.array([b*math.cos(self.theta)-radius*math.sin(self.theta),
                          b*math.sin(self.theta)+radius*math.cos(self.theta)])*rate
        spiral=radius*np.array([math.cos(self.theta),math.sin(self.theta)])
        raw_target=spiral+correction
        target,feedforward=bounded_target(raw_target,tangent+base[:2],c.spiral_radius_m)
        tracking=c.search_tracking_gain_s*(target-delta[:2])
        self.search_composition=dict(time_s=obs.time_s,theta_rad=self.theta,
            correction_xy_m=correction.tolist(),raw_target_xy_m=raw_target.tolist(),
            target_xy_m=target.tolist(),feedforward_xy_m_s=feedforward.tolist(),tracking_xy_m_s=tracking.tolist())
        base[:2]=np.clip(feedforward+tracking,-c.search_xy_component_speed_m_s,c.search_xy_component_speed_m_s)
        base[2]=np.clip(c.axial_gain_m_s_N*(c.search_force_N+w[2]),-c.unload_speed_m_s,c.search_forward_speed_m_s)
        self.theta=min(c.spiral_radius_m/b,self.theta+rate*dt)
        return base

    def metadata(self):
        return {**super().metadata(),'name':'B2_compliant_search_v5',
            'search_target':'disk_project(spiral + admittance_offset - search_admittance_origin)',
            'target_radius_m':self.config.spiral_radius_m,'feedforward':'directional derivative of disk projection'}
