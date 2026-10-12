"""Finite next-zero-action reference check; no all-future safety claim."""
import math
import numpy as np
from .v4_action import compose_reference_command,ReferenceEnvelopeInfeasible,TOLERANCE_M
from .v4_session import V4ResidualSession
from .layered_session import LayeredReferenceSession
VERSION='residual_reference_continuation_v2'

def predict_next_search(reference_xy,previous_xy,theta,config,dt):
    ref=np.asarray(reference_xy,dtype=float);previous=np.asarray(previous_xy,dtype=float)
    if (ref.shape!=(2,) or previous.shape!=(2,) or not np.isfinite(np.r_[ref,previous]).all()
            or not np.isfinite(theta) or theta<0 or not np.isfinite(dt) or dt<=0):
        raise ValueError('Finite XY, nonnegative advanced theta and positive dt required')
    b=config.spiral_pitch_m/(2*math.pi);radius=b*theta
    target=radius*np.array([math.cos(theta),math.sin(theta)])
    rate=config.spiral_speed_m_s/math.hypot(radius,b)
    next_theta=min(config.spiral_radius_m/b,theta+rate*dt)
    next_target=b*next_theta*np.array([math.cos(next_theta),math.sin(next_theta)])
    base=np.clip((next_target-target)/dt+config.search_tracking_gain_s*(target-ref),
        -config.search_xy_component_speed_m_s,config.search_xy_component_speed_m_s)
    limited=np.clip(np.clip(base,-.001,.001),previous-.005*dt,previous+.005*dt)
    predicted=ref+limited*dt;bound=config.spiral_radius_m+TOLERANCE_M
    current_ok=np.linalg.norm(ref)<=bound;future_ok=np.linalg.norm(predicted)<=bound
    ends=bool(current_ok and not future_ok)
    return dict(reference_feasible=bool(current_ok and (future_ok or ends)),controlled_search_end=ends,
        base_xy_m_s=base.tolist(),limited_xy_m_s=limited.tolist(),predicted_reference_xy_m=predicted.tolist())

def compose_continuation_command(base,action,*,phase,enabled,previous_limited,dt,
        reference_xy=None,radius=.00012,next_theta=None,search_config=None):
    command,log=compose_reference_command(base,action,phase=phase,enabled=enabled,
        previous_limited=previous_limited,dt=dt,reference_xy=reference_xy,radius=radius)
    log.update(continuation_version=VERSION,continuation_checked=False,continuation_filtered=False,
        continuation_filter_fraction=1.)
    if phase!='SEARCH' or not enabled:return command,log
    if search_config is None or search_config.spiral_radius_m!=radius:
        raise ValueError('Matching frozen search configuration required')
    ref=np.asarray(reference_xy);low=np.asarray(log['zero_residual_limited_command'])
    high=np.asarray(log['predicted_limited_command'])
    def check(v):return predict_next_search(ref+v[:2]*dt,v[:2],next_theta,search_config,dt)
    # The compositor proves the issued step inside the disk. The common
    # controller now ends SEARCH whenever its next step is infeasible, so
    # additional residual shrinking for that next step is unnecessary.
    baseline=check(low);future=check(high)
    log.update(continuation_checked=True,
        next_zero_reference_feasible=future['reference_feasible'],baseline_next_zero_reference_feasible=baseline['reference_feasible'],
        next_zero_controlled_search_end=future['controlled_search_end'],next_zero_limited_xy_m_s=future['limited_xy_m_s'],
        next_zero_predicted_reference_xy_m=future['predicted_reference_xy_m'],next_search_theta_rad=float(next_theta))
    return command,log

class ContinuationResidualSession(V4ResidualSession):
    def _command_for_action(self,snapshot,action):
        base=LayeredReferenceSession._command_for_action(self,snapshot,action)
        phase=snapshot.controller_state['phase'];ref=None
        if phase=='SEARCH' and snapshot.residual_enabled:
            ref=(self.env.reference[:3]-self.initial-self.controller.search_origin)[:2]
        try:
            command,log=compose_continuation_command(base,action,phase=phase,enabled=snapshot.residual_enabled,
                previous_limited=self.env.command.copy(),dt=self.env.config.control_period,reference_xy=ref,
                radius=self.controller.config.spiral_radius_m,next_theta=self.controller.theta,
                search_config=self.controller.config)
        except ReferenceEnvelopeInfeasible:
            reason='RESIDUAL_REFERENCE_INFEASIBLE'
            self.controller._fail(self.policy_observation(self.env.observe()),reason);self._finish(reason)
            command,log=compose_continuation_command([0.]*6,action,phase='FAILED',enabled=False,
                previous_limited=self.env.command.copy(),dt=self.env.config.control_period)
            log['reference_failure']=reason
        self.last_action_log=log;self.previous_residual=np.asarray(log['applied_residual'])[[0,1,3,4]].tolist()
        return command
