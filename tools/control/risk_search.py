"""Opt-in common B2 revision: sustained loaded rotation initiates unloading."""
from dataclasses import dataclass, asdict
import math
import numpy as np

from tools.control.search_recovery import Observation, SearchRecovery


@dataclass(frozen=True)
class PoseObservation(Observation):
    relative_rotation_rad: float


@dataclass(frozen=True)
class RotationRiskConfig:
    angle_rad: float = math.radians(1.5)
    axial_force_N: float = .015
    hold_s: float = .05

    def __post_init__(self):
        if any(isinstance(v,bool) or not math.isfinite(v) or v<=0 for v in asdict(self).values()):
            raise ValueError('Positive finite risk thresholds required')
        if self.angle_rad>=math.radians(2.5) or self.axial_force_N>=.025:
            raise ValueError('Risk trigger must precede the unchanged common guards')


class RiskSearchRecovery(SearchRecovery):
    # New trial entries opt in; inherited controllers keep the frozen behavior.
    warning_only=False

    def __init__(self, config=None, risk_config=None):
        super().__init__(config)
        self.risk_config=risk_config or RotationRiskConfig()
        self.risk_since=None
        self.risk_warned=False

    def command(self, obs, dt):
        if not isinstance(obs,PoseObservation):
            raise ValueError('Relative rotation sensor observation required')
        p=np.asarray(obs.displacement_m);w=np.asarray(obs.wrench_M)
        if (p.shape!=(3,) or w.shape!=(6,) or
                not np.isfinite(np.r_[p,w,obs.time_s,dt,obs.relative_rotation_rad]).all() or dt<=0 or
                not 0<=obs.relative_rotation_rad<=math.pi):
            raise ValueError('Invalid pose observation or period')
        if type(self.warning_only) is not bool:
            raise ValueError('Explicit Boolean rotation-risk warning mode required')
        r=self.risk_config
        risk=(self.phase=='INSERT' and obs.relative_rotation_rad>=r.angle_rad and w[2]<=-r.axial_force_N)
        if not risk:
            self.risk_since=None
            self.risk_warned=False
        else:
            if self.risk_since is None:self.risk_since=obs.time_s
            if obs.time_s-self.risk_since>=r.hold_s-1e-12:
                if self.warning_only:
                    if not self.risk_warned:
                        # Do not transition: INSERT elapsed time and permissions
                        # remain unchanged, and normal stall/search logic runs once.
                        self.events.append(dict(time_s=obs.time_s,phase=self.phase,
                            reason='LOADED_ROTATION_WARNING',
                            relative_rotation_rad=float(obs.relative_rotation_rad),
                            axial_force_N=float(w[2]),risk_since_s=self.risk_since))
                        self.risk_warned=True
                else:
                    if self.search_count_exhausted():
                        return self._fail(obs,'SEARCH_BUDGET_EXHAUSTED')
                    self._transition('UNLOAD',obs,'LOADED_ROTATION_RISK')
                    self.events[-1].update(relative_rotation_rad=float(obs.relative_rotation_rad),
                                           axial_force_N=float(w[2]),risk_since_s=self.risk_since)
                    self.risk_since=None
        command=super().command(obs,dt)
        if self.warning_only and self.phase!='INSERT':
            self.risk_since=None
            self.risk_warned=False
        return command

    def metadata(self):
        result={**super().metadata(), 'name':'B2_loaded_rotation_unload_v2',
                'rotation_risk':asdict(self.risk_config),
                'observations':['time','relative_displacement','wrench_M','relative_rotation_from_start'],
                'uses_hole_pose_truth':False}
        if self.warning_only:
            result.update(name='B2_loaded_rotation_warning_v1',rotation_risk_warning_only=True)
        return result
