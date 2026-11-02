"""Bounded B2 candidate. Observations exclude target/geometry ground truth."""
from collections import deque
from dataclasses import dataclass, asdict
import math
import numpy as np
from tools.control.fixed_admittance import FixedAdmittance


@dataclass(frozen=True)
class SearchConfig:
    stall_window_s: float=.4
    stall_earliest_s: float=.6
    stall_advance_m: float=5e-6
    stall_axial_force_N: float=.005
    unload_speed_m_s: float=.00025
    unload_time_s: float=1.
    unload_axial_force_N: float=.005
    unload_total_force_N: float=.01
    search_force_N: float=.008
    axial_gain_m_s_N: float=.05
    search_forward_speed_m_s: float=.0005
    spiral_pitch_m: float=40e-6
    spiral_radius_m: float=120e-6
    spiral_speed_m_s: float=.00015
    search_tracking_gain_s: float=5.
    search_xy_component_speed_m_s: float=.0003
    search_time_s: float=8.
    search_exit_advance_m: float=.0001
    max_searches: int=2
    search_actual_xy_limit_m: float=.0002
    wait_stable_s: float=1.
    recovery_min_actual_m: float=.0002
    total_action_time_s: float=20.
    settle_time_s: float=1.

    def __post_init__(self):
        if any(not math.isfinite(v) or v<=0 for v in asdict(self).values()):raise ValueError('Positive finite parameters required')
        if type(self.max_searches) is not int or self.max_searches not in (1,2):raise ValueError('At most one retry')
        if not self.unload_axial_force_N<self.search_force_N<.025:raise ValueError('Invalid load targets')
        if self.spiral_radius_m>=self.search_actual_xy_limit_m:raise ValueError('Search requires excursion allowance')


@dataclass(frozen=True)
class Observation:
    time_s: float
    displacement_m: tuple
    wrench_M: tuple


class SearchRecovery:
    def __init__(self,config=None):
        self.config=config or SearchConfig()
        self.admittance=FixedAdmittance()
        self.phase='INSERT';self.reason=None;self.events=[];self.history=deque()
        self.search_count=0;self.phase_start=0.;self.theta=0.;self.search_origin=None

    def _transition(self,phase,obs,reason):
        self.phase=phase;self.phase_start=obs.time_s
        self.events.append({'time_s':obs.time_s,'phase':phase,'reason':reason})

    def _fail(self,obs,reason):
        self.reason=reason;self._transition('FAILED',obs,reason)
        return np.zeros(6)

    def _start_search(self,obs):
        self.search_count+=1;self.search_origin=np.array(obs.displacement_m);self.theta=0.
        self._transition('SEARCH',obs,'LOW_LOAD_SEARCH')

    def start_recovered_search(self,obs):
        if self.phase!='WAIT_RECOVERY' or self.search_count>=self.config.max_searches:
            raise RuntimeError('No recovery retry available')
        self._start_search(obs)

    def command(self,obs,dt):
        c=self.config;p=np.asarray(obs.displacement_m);w=np.asarray(obs.wrench_M)
        if p.shape!=(3,) or w.shape!=(6,) or not np.isfinite(np.r_[p,w,obs.time_s,dt]).all() or dt<=0:
            raise ValueError('Invalid sensor observation or period')
        if self.phase in ('FAILED','WAIT_RECOVERY'):return np.zeros(6)
        if self.phase=='INSERT':
            self.history.append((obs.time_s,float(p[2])))
            while len(self.history)>1 and self.history[1][0]<=obs.time_s-c.stall_window_s:self.history.popleft()
            old_t,old_z=self.history[0]
            if (obs.time_s>=c.stall_earliest_s and obs.time_s-old_t>=c.stall_window_s-1e-9
                    and p[2]-old_z<c.stall_advance_m and w[2]<-c.stall_axial_force_N):
                if self.search_count>=c.max_searches:return self._fail(obs,'SEARCH_BUDGET_EXHAUSTED')
                self._transition('UNLOAD',obs,'AXIAL_STALL')
            else:return self.admittance.command(w,dt)
        if self.phase=='UNLOAD':
            if obs.time_s-self.phase_start>=c.unload_time_s:return self._fail(obs,'UNLOAD_TIMEOUT')
            if abs(w[2])<=c.unload_axial_force_N and np.linalg.norm(w[:3])<=c.unload_total_force_N:
                self._start_search(obs)
            else:
                # XY is disabled while unloading; only advance active angular channels.
                previous_xy_offset=self.admittance.offset[:2].copy()
                previous_xy_velocity=self.admittance.velocity[:2].copy()
                base=self.admittance.command(w,dt)
                self.admittance.offset[:2]=previous_xy_offset
                self.admittance.velocity[:2]=previous_xy_velocity
                return np.array([0.,0.,-c.unload_speed_m_s,base[3],base[4],0.])
        if self.phase=='SEARCH':
            delta=p-self.search_origin
            if np.linalg.norm(delta[:2])>c.search_actual_xy_limit_m:return self._fail(obs,'SEARCH_EXCURSION_LIMIT')
            if self._search_advanced(obs):
                self.history.clear();self._transition('INSERT',obs,'SEARCH_ADVANCED')
                return self.admittance.command(w,dt)
            b=c.spiral_pitch_m/(2*math.pi);radius=b*self.theta
            if radius>=c.spiral_radius_m-1e-12 or obs.time_s-self.phase_start>=c.search_time_s:
                if self.search_count>=c.max_searches:return self._fail(obs,'SEARCH_BUDGET_EXHAUSTED')
                self._transition('WAIT_RECOVERY',obs,'SEARCH_EXHAUSTED');return np.zeros(6)
            return self._search_command(obs,dt)
        raise RuntimeError('Unknown search state')

    def _search_advanced(self,obs):
        return np.asarray(obs.displacement_m)[2]-self.search_origin[2]>=self.config.search_exit_advance_m

    def _search_command(self,obs,dt):
        """Normal SEARCH only; all phase, excursion and budget gates ran first."""
        c=self.config;w=np.asarray(obs.wrench_M);delta=np.asarray(obs.displacement_m)-self.search_origin
        b=c.spiral_pitch_m/(2*math.pi);radius=b*self.theta
        base=self.admittance.command(w,dt)
        theta_rate=c.spiral_speed_m_s/math.hypot(radius,b)
        tangent=np.array([b*math.cos(self.theta)-radius*math.sin(self.theta),
                          b*math.sin(self.theta)+radius*math.cos(self.theta)])*theta_rate
        target=radius*np.array([math.cos(self.theta),math.sin(self.theta)])
        base[:2]=np.clip(base[:2]+tangent+c.search_tracking_gain_s*(target-delta[:2]),
                         -c.search_xy_component_speed_m_s,c.search_xy_component_speed_m_s)
        base[2]=np.clip(c.axial_gain_m_s_N*(c.search_force_N+w[2]),-c.unload_speed_m_s,c.search_forward_speed_m_s)
        self.theta=min(c.spiral_radius_m/b,self.theta+theta_rate*dt)
        return base

    def metadata(self):
        return {'name':'B2_bounded_search_recovery','config':asdict(self.config),
                'admittance':self.admittance.metadata(),'observations':['time','relative_displacement','wrench_M'],
                'uses_hole_pose_truth':False,'calibrated':False}


def resume_after_recovery(env,min_actual_retraction):
    """Resume only a normal, completed B2 recovery; never clear a safety fault.

    The old environment is intentionally untouched. Only its reference/command
    phase changes; real pose, velocity, elapsed time, peaks and history persist.
    """
    if latched_contact_guard(env):raise RuntimeError('Historical contact limit forbids recovery resume')
    c=env.config;r=env.observe()
    allowed={'B2_SEARCH_EXHAUSTED','RECOVERY_ACCEPTED','RECOVERY_DISTANCE_REACHED'}
    if (not env._state_valid() or env.phase!='STOPPING' or env.recovery_count!=1
            or not env.events or env.events[-1]['reason']!='RECOVERY_DISTANCE_REACHED'
            or any(e['reason'] not in allowed for e in env.events)
            or env.recovery_start is None or env.recovery_start[2]-env.data.qpos[2]<min_actual_retraction
            or np.linalg.norm(r['velocity_world'][:3])>c.stopped_speed
            or np.linalg.norm(r['velocity_world'][3:])>c.stopped_angular_speed
            or np.linalg.norm(r['contact_wrench_M'][:3])>c.recovery_force_N
            or np.linalg.norm(r['contact_wrench_G'][3:])>c.stop_torque_Nm
            or r['penetration_m']>=c.stop_penetration_m):
        raise RuntimeError('Recovery resume preconditions not met')
    env.reference=env.data.qpos.copy();env.command[:]=0;env.raw_command[:]=0
    env.phase='RUNNING';env.events.append({'time_s':float(env.data.time),'phase':'RUNNING','reason':'B2_RECOVERY_RESUMED'})


def latched_contact_guard(env):
    """Keep physical-step excursions latched even while the old core is stopping."""
    limits=(('force_N','stop_force_N','FORCE_LIMIT'),('torque_G_Nm','stop_torque_Nm','TORQUE_LIMIT'),
            ('penetration_m','stop_penetration_m','PENETRATION_LIMIT'))
    reasons=[reason for key,limit,reason in limits if env.peaks[key]>getattr(env.config,limit)]
    return '+'.join(reasons) if reasons else None
