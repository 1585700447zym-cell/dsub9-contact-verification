"""Opt-in joint XY reference bounds; the archived Cartesian core stays intact."""
import math
import numpy as np
from .safety import limit_command, shift_wrench

VERSION = 'search_reference_intersection_v1'
TOLERANCE_M = 1e-12


class ReferenceIntersectionEmpty(ValueError):
    """The live lead box no longer intersects the current search disk."""


def constrain_xy(desired, actual, center, radius, lead):
    """Keep legacy box clipping when feasible, else bound along a box segment.

    Both endpoints are in the lead box. Moving toward its closest point to the
    disk center guarantees a feasible segment when the intersection is nonempty.
    This is a bounded correction, not a claim of nearest Euclidean projection.
    """
    desired, actual, center = (np.asarray(value, dtype=float) for value in (desired, actual, center))
    if (any(value.shape != (2,) or not np.isfinite(value).all() for value in (desired, actual, center))
            or any(isinstance(value, bool) or not math.isfinite(value) or value <= 0 for value in (radius, lead))):
        raise ValueError('Finite XY coordinates and positive radius/lead required')
    low, high = actual-lead, actual+lead
    candidate = np.clip(desired, low, high)
    if np.linalg.norm(candidate-center) <= radius + TOLERANCE_M:
        return candidate
    anchor = np.clip(center, low, high)
    if np.linalg.norm(anchor-center) > radius + TOLERANCE_M:
        raise ReferenceIntersectionEmpty('Search disk and current XY lead box do not intersect')
    left, right = 0., 1.
    for _ in range(48):
        middle = (left+right)/2
        if np.linalg.norm(anchor+middle*(candidate-anchor)-center) <= radius:
            left = middle
        else:
            right = middle
    return anchor+left*(candidate-anchor)


class ReferenceEnvelopeMixin:
    reference_consistency_version = VERSION

    def __init__(self, *args, **kwargs):
        self._clear_reference_envelope()
        super().__init__(*args, **kwargs)

    def _clear_reference_envelope(self):
        self.search_reference_center = self.search_reference_radius = None
        self.reference_failure_pending = False
        self.reference_envelope_corrections = 0
        self.reference_envelope_last = None

    def reset(self, *args, **kwargs):
        self._clear_reference_envelope()
        return super().reset(*args, **kwargs)

    def configure_search_envelope(self, center, radius=None):
        if center is None:
            self.search_reference_center = self.search_reference_radius = None
            return
        center = np.asarray(center, dtype=float)
        if center.shape != (2,) or not np.isfinite(center).all() or radius != .0004:
            raise ValueError('This repair keeps the existing 400um SEARCH radius')
        self.search_reference_center, self.search_reference_radius = center.copy(), radius

    def stop(self, reason='REQUESTED_STOP'):
        self.configure_search_envelope(None)
        return super().stop(reason)

    def _bound_search_reference(self):
        if self.search_reference_center is None or self.phase != 'RUNNING':
            return True
        desired = self.reference[:2].copy()
        try:
            bounded = constrain_xy(desired, self.data.qpos[:2], self.search_reference_center,
                                   self.search_reference_radius, self.config.reference_lead_m)
        except ReferenceIntersectionEmpty:
            self.reference_failure_pending = True
            self.reference_envelope_last = dict(result='INFEASIBLE', time_s=float(self.data.time),
                actual_xy_m=self.data.qpos[:2].tolist(), center_xy_m=self.search_reference_center.tolist())
            # Preserve the existing recovery event whitelist; details stay separate.
            self.stop('B2_SEARCH_EXHAUSTED')
            return False
        if not np.array_equal(desired, bounded):
            self.reference_envelope_corrections += 1
            self.reference_envelope_last = dict(result='BOUNDED', time_s=float(self.data.time),
                requested_xy_m=desired.tolist(), bounded_xy_m=bounded.tolist(),
                actual_xy_m=self.data.qpos[:2].tolist(), center_xy_m=self.search_reference_center.tolist())
            self.reference[:2] = bounded
        return True

    def reference_envelope_state(self):
        return dict(version=VERSION, active=self.search_reference_center is not None and self.phase == 'RUNNING',
                    corrections=self.reference_envelope_corrections, infeasible=self.reference_failure_pending)

    def metadata(self):
        return {**super().metadata(), 'reference_consistency': self.reference_envelope_state(),
                'last_reference_correction': self.reference_envelope_last}

    # Frozen Cartesian step copied here only to add pre-PD/post-step XY hooks.
    # Original source SHA256: bc06000c5ce82de6fdb2d3cee111131481ec58d6ac3d038e73c23c75b38db935
    def step(self, command_world):
        if self.search_reference_center is None or self.phase != 'RUNNING':
            return super().step(command_world)
        import mujoco
        if self.phase in ('UNINITIALIZED','TERMINAL'):raise RuntimeError('No active episode')
        if not self._state_valid():
            self._terminate('INVALID_SIMULATION');return self.observe()
        try:
            requested=np.asarray(command_world,dtype=float)
        except (ValueError,TypeError,OverflowError) as error:
            self._terminate('INVALID_COMMAND');raise ValueError('Command conversion failed') from error
        if requested.shape!=(6,) or not np.isfinite(requested).all():
            self._terminate('INVALID_COMMAND');raise ValueError('Command must be finite shape6')
        self.raw_command=requested.copy()
        if self.phase=='STOPPING':requested=np.zeros(6)
        if self.phase=='RETRACT':requested=np.array([0,0,-self.config.recovery_speed,0,0,0])
        limited=limit_command(requested,self.command,self.config.control_period,
                              self.velocity_limits,self.acceleration_limits)
        if not np.allclose(limited,requested,rtol=0,atol=1e-15):self.command_limited_steps+=1
        self.command=limited
        for _ in range(round(self.config.control_period/self.config.timestep)):
            # Advance only the command reference; actual pose is integrated below.
            target_r=np.zeros(9);mujoco.mju_quat2Mat(target_r,self.reference[3:])
            reference_velocity=np.r_[self.command[:3],target_r.reshape(3,3).T@self.command[3:]]
            mujoco.mj_integratePos(self.model,self.reference,reference_velocity,self.config.timestep)
            error=np.zeros(6);mujoco.mj_differentiatePos(self.model,error,1.,self.data.qpos,self.reference)
            limits=np.array([self.config.reference_lead_m]*3+[self.config.reference_lead_rad]*3)
            clipped=np.clip(error,-limits,limits)
            if not np.array_equal(error,clipped):
                self.reference_limited_steps+=1;self.reference=self.data.qpos.copy()
                mujoco.mj_integratePos(self.model,self.reference,clipped,1.)
            if self._bound_search_reference():
                clipped[:2] = self.reference[:2]-self.data.qpos[:2]
            else:
                clipped[:] = 0.
            r=self.data.xmat[self.male].reshape(3,3)
            error_world=np.r_[clipped[:3],r@clipped[3:]]
            velocity=np.r_[self.data.qvel[:3],r@self.data.qvel[3:]]
            raw=self.kp*error_world+self.kd*(self.command-velocity)
            self.drive=np.clip(raw,-self.effort_limits,self.effort_limits)
            if not np.array_equal(raw,self.drive):self.drive_saturation_steps+=1
            p=self.data.xpos[self.male];g=p+r@self.grasp_local
            at_g=shift_wrench(self.drive,p,g)
            self.data.qfrc_applied[:]=0
            mujoco.mj_applyFT(self.model,self.data,at_g[:3],at_g[3:],g,self.male,self.data.qfrc_applied)
            try:
                mujoco.mj_step(self.model,self.data)
                mujoco.mj_forward(self.model,self.data)
            except mujoco.FatalError:
                self._terminate('SIMULATION_ERROR');break
            self.physical_steps+=1
            if not self._state_valid():
                self._terminate('INVALID_SIMULATION');break
            self._bound_search_reference()
            row=self._read()
            if np.isfinite(self.data.qpos).all() and np.isfinite(self.data.qvel).all() and np.isfinite(row['contact_wrench_G']).all():
                self.last_finite=row;self._record_peaks(row)
            self._guard(row)
            if self.phase=='TERMINAL':break
            if self.phase=='RETRACT' and self.recovery_start[2]-self.reference[2]>=self.config.recovery_distance_m:
                self.stop('RECOVERY_DISTANCE_REACHED')
            if self.phase=='RETRACT' and self.data.time-self.recovery_start_time>=self.config.recovery_time_limit_s:
                self.stop('RECOVERY_TIME_LIMIT')
        return self.observe()
