"""Versioned recovery exit gate; keep the frozen V1 controller untouched."""
from collections import deque
from dataclasses import asdict, dataclass
import math

import numpy as np

from tools.control.search_recovery import SearchRecovery


@dataclass(frozen=True)
class ExitGateConfig:
    hold_s: float = .05
    min_progress_m: float = 5e-6
    max_force_N: float = .01

    def __post_init__(self):
        if any(not math.isfinite(v) or v <= 0 for v in asdict(self).values()):
            raise ValueError('Positive finite exit parameters required')
        if self.max_force_N >= .025:
            raise ValueError('Exit qualification must be below the force stop threshold')


class SearchRecoveryV2(SearchRecovery):
    def __init__(self, config=None, exit_gate=None):
        super().__init__(config)
        self.exit_gate = exit_gate or ExitGateConfig()
        self.blocked_z_m = None
        self.recovered_search = False
        self.exit_history = deque()
        self.exit_evidence = None

    def _transition(self, phase, obs, reason):
        if phase == 'UNLOAD' and reason == 'AXIAL_STALL':
            z = float(obs.displacement_m[2])
            self.blocked_z_m = z if self.blocked_z_m is None else max(self.blocked_z_m, z)
        super()._transition(phase, obs, reason)
        self.events[-1]['blocked_z_m'] = self.blocked_z_m
        if reason == 'SEARCH_ADVANCED' and self.recovered_search:
            self.events[-1]['exit_evidence'] = dict(self.exit_evidence)

    def _start_search(self, obs):
        self.recovered_search = False
        self.exit_history.clear()
        self.exit_evidence = None
        super()._start_search(obs)

    def start_recovered_search(self, obs):
        super().start_recovered_search(obs)
        self.recovered_search = True
        self.events[-1]['recovered_search'] = True

    def _search_can_exit(self, obs, dt):
        z = float(obs.displacement_m[2])
        if not self.recovered_search:
            return z - self.search_origin[2] >= self.config.search_exit_advance_m
        if self.blocked_z_m is None:
            return False
        threshold = max(float(self.search_origin[2]), self.blocked_z_m) + self.config.search_exit_advance_m
        force = float(np.linalg.norm(obs.wrench_M[:3]))
        if z < threshold or force > self.exit_gate.max_force_N:
            self.exit_history.clear()
            return False
        if self.exit_history:
            last_t, last_z, _ = self.exit_history[-1]
            gap = obs.time_s - last_t
            if gap <= 0 or gap > dt + 1e-9 or z < last_z - 1e-12:
                self.exit_history.clear()
        self.exit_history.append((obs.time_s, z, force))
        while len(self.exit_history) > 1 and self.exit_history[1][0] <= obs.time_s - self.exit_gate.hold_s:
            self.exit_history.popleft()
        start_t, start_z, _ = self.exit_history[0]
        duration = obs.time_s - start_t
        advance = z - start_z
        if duration >= self.exit_gate.hold_s - 1e-9 and advance >= self.exit_gate.min_progress_m:
            self.exit_evidence = {'blocked_z_m': self.blocked_z_m, 'threshold_z_m': threshold,
                                  'exit_z_m': z, 'duration_s': duration, 'advance_m': advance,
                                  'max_observed_force_N': max(h[2] for h in self.exit_history)}
            return True
        return False

    def metadata(self):
        result = super().metadata()
        result.update(name='B2_recovery_exit_v2', exit_gate=asdict(self.exit_gate),
                      recovery_exit_rule='historical_blocked_depth_plus_original_margin_and_sustained_low_load_progress')
        return result


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
            if self._search_can_exit(obs,dt):
                self.history.clear();self._transition('INSERT',obs,'SEARCH_ADVANCED')
                return self.admittance.command(w,dt)
            b=c.spiral_pitch_m/(2*math.pi);radius=b*self.theta
            if radius>=c.spiral_radius_m-1e-12 or obs.time_s-self.phase_start>=c.search_time_s:
                if self.search_count>=c.max_searches:return self._fail(obs,'SEARCH_BUDGET_EXHAUSTED')
                self._transition('WAIT_RECOVERY',obs,'SEARCH_EXHAUSTED');return np.zeros(6)
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
        raise RuntimeError('Unknown search state')
