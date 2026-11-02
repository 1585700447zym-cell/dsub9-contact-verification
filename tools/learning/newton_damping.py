"""N2 drive-release repair; keeps the archived N1 candidate and its evidence."""
from dataclasses import dataclass, replace
import math

import numpy as np

from tools.learning.newton_profile import NewtonProfile as N1Profile


def explicit_drive_stable(stiffness, damping, mass, timestep):
    values = (stiffness, damping, mass, timestep)
    if not all(math.isfinite(v) and v > 0 for v in values):
        return False
    return timestep*timestep*stiffness/mass+2*timestep*damping/mass < 4.


def release_velocity_peak(stiffness, damping, mass, lead):
    if not all(math.isfinite(v) and v > 0 for v in (stiffness,damping,mass,lead)):
        raise ValueError('Positive finite drive coefficients required')
    critical = 2*math.sqrt(stiffness*mass)
    if math.isclose(damping, critical, rel_tol=1e-12):
        return lead*math.sqrt(stiffness/mass)/math.e
    if damping < critical:
        raise ValueError('This diagnostic requires critical or overdamped drive')
    discriminant = math.sqrt(damping*damping-4*mass*stiffness)
    slow = -2*stiffness/(damping+discriminant)
    fast = -(damping+discriminant)/(2*mass)
    time_peak = math.log(fast/slow)/(slow-fast)
    return abs(lead*slow*fast*(math.exp(slow*time_peak)-math.exp(fast*time_peak))/(fast-slow))


def discrete_release_peak(stiffness, damping, mass, timestep, lead, command):
    """Worst aligned free-axis release, including explicit PD feedforward.

    This is a deterministic scalar diagnostic, not a nonlinear contact proof.
    The actual MuJoCo guards remain active on every physical integration step.
    """
    if not explicit_drive_stable(stiffness,damping,mass,timestep):
        raise ValueError('Unstable explicit free drive')
    position, reference, velocity, peak = 0., lead, 0., 0.
    for _ in range(math.ceil(1./timestep)):
        reference += command*timestep
        error = min(lead, max(-lead, reference-position))
        reference = position+error
        velocity += timestep*(stiffness*error+damping*(command-velocity))/mass
        position += timestep*velocity
        peak = max(peak, abs(velocity))
    return peak


@dataclass(frozen=True)
class NewtonProfile(N1Profile):
    translational_damping_ratio: float = 5.
    rotational_damping_ratio: float = 12.
    reference_lead_m: float = .00012
    reference_lead_rad: float = .01

    def __post_init__(self):
        super().__post_init__()
        if min(self.translational_damping_ratio,self.rotational_damping_ratio) < 1:
            raise ValueError('N2 requires at least critical damping')

    def metadata(self):
        return {**super().metadata(), 'id':'newton_force_N2_damped_v1',
                'repair':'explicit drive damping and reduced stored reference error',
                'nonlinear_contact_robustness_proven':False}


def environment_class():
    from tools.learning.newton_profile import environment_class as original_environment
    Base = original_environment()

    class DampedNewtonEnvironment(Base):
        def __init__(self, profile=None):
            p = profile or NewtonProfile()
            super().__init__(p)
            self.config = replace(self.config, reference_lead_m=p.reference_lead_m,
                                  reference_lead_rad=p.reference_lead_rad)
            self.kd *= np.array([p.translational_damping_ratio]*3+[p.rotational_damping_ratio]*3)
            inertias = [float(self.model.body_mass[self.male])]*3+self.model.body_inertia[self.male].tolist()
            limits = [p.reference_lead_m]*3+[p.reference_lead_rad]*3
            self.release_diagnostics = []
            for axis,(k,c,m,lead,speed) in enumerate(zip(self.kp,self.kd,inertias,limits,self.velocity_limits)):
                stable = explicit_drive_stable(k,c,m,p.timestep)
                peak = discrete_release_peak(k,c,m,p.timestep,lead,speed) if stable else math.inf
                guard = self.config.actual_speed_limit if axis < 3 else self.config.actual_angular_speed_limit
                if not stable or math.sqrt(3)*peak >= guard:
                    raise ValueError('N2 free drive release violates stability or motion guard')
                self.release_diagnostics.append(dict(axis=axis,k=float(k),c=float(c),mass_or_inertia=m,
                    discrete_peak=float(peak),aligned_three_axis_norm=math.sqrt(3)*peak,guard=guard))

        def begin_cycle(self):
            super().begin_cycle()
            self.cycle_peaks.update(force_min_N=math.inf,force_max_N=0.,
                                    axial_min_N=math.inf,axial_max_N=-math.inf)

        def _record_peaks(self, row):
            super()._record_peaks(row)
            force = float(np.linalg.norm(row['contact_wrench_M'][:3]))
            axial = -float(row['contact_wrench_M'][2])
            self.cycle_peaks['force_min_N'] = min(self.cycle_peaks['force_min_N'],force)
            self.cycle_peaks['force_max_N'] = max(self.cycle_peaks['force_max_N'],force)
            self.cycle_peaks['axial_min_N'] = min(self.cycle_peaks['axial_min_N'],axial)
            self.cycle_peaks['axial_max_N'] = max(self.cycle_peaks['axial_max_N'],axial)

        def metadata(self):
            return {**super().metadata(), 'effective_kd':self.kd.tolist(),
                    'drive_release_diagnostics':self.release_diagnostics}
    return DampedNewtonEnvironment
