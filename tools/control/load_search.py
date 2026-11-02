"""Opt-in B2 revision: bounded relief of excessive lateral search loading."""
from dataclasses import dataclass,asdict
import math
import numpy as np

from tools.control.risk_search import RiskSearchRecovery,PoseObservation


@dataclass(frozen=True)
class SearchLoadConfig:
    lateral_force_N: float = .012
    total_force_N: float = .022
    hold_s: float = .02

    def __post_init__(self):
        if any(isinstance(v,bool) or not math.isfinite(v) or v<=0 for v in asdict(self).values()):
            raise ValueError('Positive finite search load thresholds required')
        if not self.lateral_force_N<self.total_force_N<.025:
            raise ValueError('Load thresholds must precede the common force guard')


class LoadSearchRecovery(RiskSearchRecovery):
    def __init__(self,config=None,risk_config=None,load_config=None):
        super().__init__(config,risk_config)
        self.load_config=load_config or SearchLoadConfig()
        self.load_since=None
        self.reference_release_requested=False

    def command(self,obs,dt):
        # Validate before touching phase/timers; the superclass also validates.
        if not isinstance(obs,PoseObservation):raise ValueError('Relative pose observation required')
        p=np.asarray(obs.displacement_m);w=np.asarray(obs.wrench_M)
        if (p.shape!=(3,) or w.shape!=(6,) or
                not np.isfinite(np.r_[p,w,obs.time_s,dt,obs.relative_rotation_rad]).all() or dt<=0 or
                not 0<=obs.relative_rotation_rad<=math.pi):
            raise ValueError('Invalid observation or period')
        if self.reference_release_requested:
            raise RuntimeError('Session must consume the reference release before another control call')
        if self.phase=='SEARCH':
            # Preserve original excursion -> advance -> exhaustion priority.
            # New relief must not replace mandatory recovery or extend a search.
            delta=p-self.search_origin;c=self.config
            radius=c.spiral_pitch_m*self.theta/(2*math.pi)
            if (np.linalg.norm(delta[:2])>c.search_actual_xy_limit_m or
                    self._search_advanced(obs) or radius>=c.spiral_radius_m-1e-12 or
                    obs.time_s-self.phase_start>=c.search_time_s):
                self.load_since=None
                return super().command(obs,dt)
        c=self.load_config
        lateral=float(np.linalg.norm(w[:2]));total=float(np.linalg.norm(w[:3]))
        loaded=self.phase=='SEARCH' and lateral>=c.lateral_force_N and total>=c.total_force_N
        if not loaded:self.load_since=None
        else:
            if self.load_since is None:self.load_since=obs.time_s
            if obs.time_s-self.load_since>=c.hold_s-1e-12:
                if self.search_count>=self.config.max_searches:
                    return self._fail(obs,'SEARCH_BUDGET_EXHAUSTED')
                self._transition('UNLOAD',obs,'SEARCH_LATERAL_LOAD')
                self.events[-1].update(lateral_force_N=lateral,total_force_N=total,load_since_s=self.load_since,
                                       search_count=self.search_count,paused_theta_rad=self.theta)
                self.reference_release_requested=True
                self.load_since=None
        return super().command(obs,dt)

    def metadata(self):
        return {**super().metadata(),'name':'B2_search_load_relief_v3',
                'search_load':asdict(self.load_config),'requires_xy_reference_release':True,
                'search_budget_extended':False}
