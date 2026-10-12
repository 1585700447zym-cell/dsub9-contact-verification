"""Common residual compositor with a one-step SEARCH reference constraint."""
import numpy as np
from .action import compose_command
from tools.dynamics.safety import limit_command

SCALE=(.00005,.00005,.0005,.0005)
VELOCITY=[.001]*3+[.03]*3
ACCELERATION=[.005]*3+[.3]*3
TOLERANCE_M=1e-12

class ReferenceEnvelopeInfeasible(RuntimeError):
    pass

def compose_reference_command(base,action,*,phase,enabled,previous_limited,dt,reference_xy=None,radius=.00012):
    command,log=compose_command(base,action,phase=phase,enabled=enabled,previous_limited=previous_limited,dt=dt,action_scale=SCALE)
    log.update(reference_filter_fraction=1.,reference_checked=False,unfiltered_stage_limited_total=list(command))
    if phase!='SEARCH' or not enabled:return command,log
    ref=np.asarray(reference_xy,dtype=float)
    if ref.shape!=(2,) or not np.isfinite(ref).all() or not np.isfinite(radius) or radius<=0:
        raise ValueError('Finite SEARCH reference XY and positive radius required')
    low=np.array(log['zero_residual_limited_command']);high=np.array(log['predicted_limited_command'])
    bound=radius+TOLERANCE_M
    def inside(v):return bool(np.linalg.norm(ref+v[:2]*dt)<=bound)
    if np.linalg.norm(ref)>bound or not inside(low):
        raise ReferenceEnvelopeInfeasible('Zero-residual drive prediction outside SEARCH reference disk')
    log.update(reference_checked=True,reference_xy_m=ref.tolist(),reference_radius_limit_m=radius)
    if not inside(high):
        # Limited velocities lie in a convex speed/slew box. Intersect their
        # segment with the convex reference disk, so feasibility is an interval.
        # Do not consume the controller's roundoff tolerance as control space.
        # If the baseline is already in that tiny tolerance shell, retain it.
        inner_bound=radius-TOLERANCE_M
        left,right=0.,1.
        if np.linalg.norm(ref+low[:2]*dt)>inner_bound:right=0.
        for _ in range(56):
            middle=(left+right)*.5
            if np.linalg.norm(ref+(low+middle*(high-low))[:2]*dt)<=inner_bound:left=middle
            else:right=middle
        command=low+left*(high-low)
        limited=limit_command(command,previous_limited,dt,VELOCITY,ACCELERATION)
        if not inside(limited):  # roundoff fallback retains a proven feasible endpoint
            left=0.;command=low.copy();limited=limit_command(command,previous_limited,dt,VELOCITY,ACCELERATION)
        if not inside(limited):raise ReferenceEnvelopeInfeasible('Final drive verification failed')
        log.update(reference_filter_fraction=left,stage_limited_total=command.tolist(),
                   predicted_limited_command=limited.tolist(),effective_command_delta=(limited-low).tolist())
    final=np.array(log['predicted_limited_command'])
    log['predicted_reference_xy_m']=(ref+final[:2]*dt).tolist()
    # applied_residual remains the permission-applied request (v3 replay meaning).
    # effective_command_delta is the actual filtered command-layer intervention.
    return command,log
