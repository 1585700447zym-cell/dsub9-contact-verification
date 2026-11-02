"""Bounded XY position search, axial force regulation and net-depth progress."""
import math
import numpy as np
from tools.control.load_search import LoadSearchRecovery
from tools.control.risk_search import PoseObservation


class AxisSearchRecovery(LoadSearchRecovery):
    def __init__(self,config=None,risk_config=None,load_config=None):
        super().__init__(config,risk_config,load_config)
        self.episode_peak_z_m=None
        self.search_progress_origin_z_m=None
        self.search_composition=None

    def command(self,obs,dt):
        # Parent validates and enforces pending release before any new depth state.
        command=super().command(obs,dt)
        z=float(obs.displacement_m[2])
        self.episode_peak_z_m=z if self.episode_peak_z_m is None else max(self.episode_peak_z_m,z)
        return command

    def _transition(self,phase,obs,reason):
        super()._transition(phase,obs,reason)
        if phase!='SEARCH':self.search_composition=None
        if reason=='SEARCH_ADVANCED':
            self.events[-1].update(progress_origin_z_m=self.search_progress_origin_z_m,
                observed_z_m=float(obs.displacement_m[2]),
                net_advance_m=float(obs.displacement_m[2])-self.search_progress_origin_z_m)

    def start_recovered_search(self,obs):
        # Public recovery entry bypasses command(), so validate before spending
        # the remaining retry or changing its frozen progress reference.
        if not isinstance(obs,PoseObservation):raise ValueError('Relative pose observation required')
        p=np.asarray(obs.displacement_m);w=np.asarray(obs.wrench_M)
        if (p.shape!=(3,) or w.shape!=(6,) or
                not np.isfinite(np.r_[p,w,obs.time_s,obs.relative_rotation_rad]).all() or
                not 0<=obs.relative_rotation_rad<=math.pi):
            raise ValueError('Invalid recovery observation')
        super().start_recovered_search(obs)

    def _start_search(self,obs):
        # Freeze before this search; do not chase the increasing current peak.
        z=float(obs.displacement_m[2])
        self.search_progress_origin_z_m=z if self.episode_peak_z_m is None else max(self.episode_peak_z_m,z)
        self.search_composition=None
        super()._start_search(obs)
        self.events[-1]['progress_origin_z_m']=self.search_progress_origin_z_m

    def _search_advanced(self,obs):
        if self.search_progress_origin_z_m is None:raise RuntimeError('Search progress origin required')
        return float(obs.displacement_m[2])-self.search_progress_origin_z_m>=self.config.search_exit_advance_m

    def _search_command(self,obs,dt):
        c=self.config;w=np.asarray(obs.wrench_M);delta=np.asarray(obs.displacement_m)-self.search_origin
        # XY is inactive in this mode. Preserve its memory for INSERT, as in UNLOAD.
        previous_xy_offset=self.admittance.offset[:2].copy()
        previous_xy_velocity=self.admittance.velocity[:2].copy()
        base=self.admittance.command(w,dt)
        self.admittance.offset[:2]=previous_xy_offset
        self.admittance.velocity[:2]=previous_xy_velocity
        b=c.spiral_pitch_m/(2*math.pi);radius=b*self.theta
        rate=c.spiral_speed_m_s/math.hypot(radius,b)
        tangent=np.array([b*math.cos(self.theta)-radius*math.sin(self.theta),
                          b*math.sin(self.theta)+radius*math.cos(self.theta)])*rate
        target=radius*np.array([math.cos(self.theta),math.sin(self.theta)])
        tracking=c.search_tracking_gain_s*(target-delta[:2])
        self.search_composition=dict(time_s=obs.time_s,theta_rad=self.theta,
            target_xy_m=target.tolist(),feedforward_xy_m_s=tangent.tolist(),tracking_xy_m_s=tracking.tolist())
        base[:2]=np.clip(tangent+tracking,-c.search_xy_component_speed_m_s,c.search_xy_component_speed_m_s)
        base[2]=np.clip(c.axial_gain_m_s_N*(c.search_force_N+w[2]),-c.unload_speed_m_s,c.search_forward_speed_m_s)
        self.theta=min(c.spiral_radius_m/b,self.theta+rate*dt)
        return base

    def metadata(self):
        return {**super().metadata(),'name':'B2_axis_search_net_progress_v6',
            'search_xy':'original bounded spiral position target; XY admittance memory frozen',
            'search_z':'original 8mN force regulation','search_angles':'original angular admittance',
            'search_exit':'100um beyond peak sensed Z frozen at each search start',
            'target_radius_m':self.config.spiral_radius_m}
