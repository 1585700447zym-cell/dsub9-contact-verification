"""Search velocity tracks the drive reference, avoiding a second error integral."""
from dataclasses import dataclass,asdict
import math
import numpy as np
from tools.control.axis_search import AxisSearchRecovery
from tools.control.risk_search import PoseObservation


@dataclass(frozen=True)
class DriveObservation(PoseObservation):
    reference_displacement_m: tuple
    previous_command_xy_m_s: tuple


@dataclass(frozen=True)
class DriveSearchConfig:
    linear_speed_m_s: float=.001
    linear_acceleration_m_s2: float=.005

    def __post_init__(self):
        if any(isinstance(v,bool) or not math.isfinite(v) or v<=0 for v in asdict(self).values()):
            raise ValueError('Positive finite drive limits required')


class ReferenceSearchRecovery(AxisSearchRecovery):
    def __init__(self,config=None,risk_config=None,load_config=None,drive_config=None):
        super().__init__(config,risk_config,load_config)
        self.drive_config=drive_config or DriveSearchConfig()

    def _validate_drive_observation(self,obs):
        if not isinstance(obs,DriveObservation):raise ValueError('Drive observation required')
        ref=np.asarray(obs.reference_displacement_m);previous=np.asarray(obs.previous_command_xy_m_s)
        p=np.asarray(obs.displacement_m);w=np.asarray(obs.wrench_M)
        if (ref.shape!=(3,) or previous.shape!=(2,) or p.shape!=(3,) or w.shape!=(6,) or
                not np.isfinite(np.r_[ref,previous,p,w,obs.time_s,obs.relative_rotation_rad]).all() or
                not 0<=obs.relative_rotation_rad<=math.pi or
                np.any(np.abs(previous)>self.drive_config.linear_speed_m_s)):
            raise ValueError('Invalid reference or previous drive command')

    def command(self,obs,dt):
        self._validate_drive_observation(obs)
        if not math.isfinite(dt) or dt<=0:raise ValueError('Positive finite drive period required')
        if self.phase=='SEARCH':
            reference=np.asarray(obs.reference_displacement_m)[:2]-self.search_origin[:2]
            if np.linalg.norm(reference)>self.config.spiral_radius_m+1e-12:
                result=self._fail(obs,'SEARCH_REFERENCE_LIMIT')
                self.events[-1].update(reference_xy_m=reference.tolist(),radius_limit_m=self.config.spiral_radius_m)
                return result
        return super().command(obs,dt)

    def start_recovered_search(self,obs):
        self._validate_drive_observation(obs)
        super().start_recovered_search(obs)

    def _search_command(self,obs,dt):
        c=self.config;d=self.drive_config;w=np.asarray(obs.wrench_M)
        reference=np.asarray(obs.reference_displacement_m)[:2]-self.search_origin[:2]
        previous=np.asarray(obs.previous_command_xy_m_s)
        b=c.spiral_pitch_m/(2*math.pi);radius=b*self.theta
        rate=c.spiral_speed_m_s/math.hypot(radius,b)
        target=radius*np.array([math.cos(self.theta),math.sin(self.theta)])
        next_theta=min(c.spiral_radius_m/b,self.theta+rate*dt)
        next_target=b*next_theta*np.array([math.cos(next_theta),math.sin(next_theta)])
        # A secant of the same spiral is consistent with discrete reference
        # integration. Euler-integrating the continuous tangent drifts radially.
        tangent=(next_target-target)/dt
        tracking=c.search_tracking_gain_s*(target-reference)
        xy=np.clip(tangent+tracking,-c.search_xy_component_speed_m_s,c.search_xy_component_speed_m_s)
        speed_limited=np.clip(xy,-d.linear_speed_m_s,d.linear_speed_m_s)
        limited=np.clip(speed_limited,previous-d.linear_acceleration_m_s2*dt,previous+d.linear_acceleration_m_s2*dt)
        predicted=reference+limited*dt
        current_radius=float(np.linalg.norm(reference));predicted_radius=float(np.linalg.norm(predicted))
        if current_radius<=c.spiral_radius_m+1e-12 and predicted_radius>c.spiral_radius_m+1e-12:
            # Residuals can reach the boundary before the final spiral segment.
            # Reuse exhaustion/recovery before issuing an infeasible SEARCH
            # command; the session performs its existing physical stop.
            self.theta=next_theta
            if self.search_count>=c.max_searches:result=self._fail(obs,'SEARCH_BUDGET_EXHAUSTED')
            else:self._transition('WAIT_RECOVERY',obs,'SEARCH_EXHAUSTED');result=np.zeros(6)
            self.events[-1].update(reference_boundary_end=True,
                reference_boundary_final_segment=next_theta>=c.spiral_radius_m/b,
                reference_xy_m=reference.tolist(),predicted_reference_xy_m=predicted.tolist(),
                radius_limit_m=c.spiral_radius_m)
            return result
        if max(current_radius,predicted_radius)>c.spiral_radius_m+1e-12:
            result=self._fail(obs,'SEARCH_REFERENCE_LIMIT')
            self.events[-1].update(reference_xy_m=reference.tolist(),predicted_reference_xy_m=predicted.tolist(),
                                   radius_limit_m=c.spiral_radius_m)
            return result
        # Keep XY inactive in admittance; angular channels advance exactly once.
        offset=self.admittance.offset[:2].copy();velocity=self.admittance.velocity[:2].copy()
        base=self.admittance.command(w,dt)
        self.admittance.offset[:2]=offset;self.admittance.velocity[:2]=velocity
        base[:2]=xy
        base[2]=np.clip(c.axial_gain_m_s_N*(c.search_force_N+w[2]),-c.unload_speed_m_s,c.search_forward_speed_m_s)
        self.search_composition=dict(time_s=obs.time_s,theta_rad=self.theta,target_xy_m=target.tolist(),
            reference_xy_m=reference.tolist(),feedforward_xy_m_s=tangent.tolist(),tracking_xy_m_s=tracking.tolist(),
            predicted_limited_xy_m_s=limited.tolist(),predicted_reference_xy_m=predicted.tolist())
        self.theta=next_theta
        return base

    def metadata(self):
        return {**super().metadata(),'name':'B2_reference_boundary_end_v8','drive_limits':asdict(self.drive_config),
            'search_xy':'spiral tangent + gain*(target - drive reference); XY admittance frozen',
            'feedforward':'finite difference between consecutive spiral target points',
            'reference_envelope':'current outside disk is a fault; infeasible next SEARCH command ends search through existing stop/recovery',
            'observations':super().metadata()['observations']+['relative_drive_reference','previous_limited_xy_command']}
