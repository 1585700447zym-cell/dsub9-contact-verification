"""Separate N1 force-domain candidate; historical models/contracts stay intact.

N1 is a simulation design, not calibrated CR5 or KWR75 hardware. No construction
here grants permission to learn from a physical rollout.
"""
from dataclasses import asdict, dataclass
import math
import xml.etree.ElementTree as ET

import numpy as np

from tools.control.search_recovery import SearchConfig
from tools.control.risk_search import RotationRiskConfig
from tools.control.load_search import SearchLoadConfig
from tools.learning.reward import EpisodeReward


def _positive(record):
    if any(isinstance(v, bool) or not math.isfinite(v) or v <= 0 for v in asdict(record).values()):
        raise ValueError('Finite positive N1 parameters required')


@dataclass(frozen=True)
class NewtonProfile:
    search_force_N: float = 2.
    force_guard_N: float = 5.
    torque_guard_Nm: float = .1
    contact_time_constant_s: float = .001
    timestep: float = .0002

    def __post_init__(self):
        _positive(self)
        if not .5 < self.search_force_N < self.force_guard_N or self.force_guard_N <= 4.4:
            raise ValueError('Working and relief loads must precede the force guard')
        if self.contact_time_constant_s < 2*self.timestep:
            raise ValueError('Contact time constant below two integration steps')
        if .002/self.timestep < 1 or not math.isclose(.002/self.timestep, round(.002/self.timestep), abs_tol=1e-10):
            raise ValueError('Integer physical steps per 2ms cycle required')

    def metadata(self):
        return dict(id='newton_force_N1_v1', **asdict(self), hardware_qualified=False,
                    geometry_changed=False, mass_inertia_changed=False, friction_changed=False,
                    training_admitted=False, force_reference='M/world', torque_guard_reference='G/world')


@dataclass(frozen=True)
class NewtonSearchConfig(SearchConfig):
    stall_axial_force_N: float = .5
    unload_axial_force_N: float = .3
    unload_total_force_N: float = .5
    search_force_N: float = 2.
    axial_gain_m_s_N: float = .00025
    total_action_time_s: float = 25.
    force_guard_N: float = 5.

    def __post_init__(self):
        _positive(self)
        if type(self.max_searches) is not int or self.max_searches not in (1, 2):
            raise ValueError('At most one search retry')
        if not self.unload_axial_force_N < self.search_force_N < self.force_guard_N:
            raise ValueError('Invalid N1 search loads')
        if max(self.stall_axial_force_N, self.unload_total_force_N) >= self.force_guard_N:
            raise ValueError('N1 phase thresholds must precede the guard')
        if self.spiral_radius_m >= self.search_actual_xy_limit_m:
            raise ValueError('Search requires actual excursion allowance')


@dataclass(frozen=True)
class NewtonRiskConfig(RotationRiskConfig):
    axial_force_N: float = 1.5
    force_guard_N: float = 5.

    def __post_init__(self):
        _positive(self)
        if self.angle_rad >= math.radians(2.5) or self.axial_force_N >= self.force_guard_N:
            raise ValueError('N1 risk must precede common guards')


@dataclass(frozen=True)
class NewtonLoadConfig(SearchLoadConfig):
    lateral_force_N: float = 2.
    total_force_N: float = 4.4
    force_guard_N: float = 5.

    def __post_init__(self):
        _positive(self)
        if not self.lateral_force_N < self.total_force_N < self.force_guard_N:
            raise ValueError('N1 relief must precede common guard')


def dynamic_config(profile=None):
    from tools.dynamics.cartesian import DynamicConfig
    p = profile or NewtonProfile()
    return DynamicConfig(collision_backend='native', timestep=p.timestep,
        translational_stiffness=20000., rotational_stiffness=2.,
        force_limit_N=8., torque_limit_Nm=.2, stop_force_N=p.force_guard_N,
        stop_torque_Nm=p.torque_guard_Nm, recovery_force_N=.5)


def build_model_xml(profile=None):
    from tools.model.clearance_task import build_task_xml
    p = profile or NewtonProfile()
    tree = ET.fromstring(build_task_xml())
    tree.set('model', 'dsub9_newton_N1_candidate_v1')
    for geom in tree.iter('geom'):
        if 'solref' in geom.attrib:
            geom.set('solref', f'{p.contact_time_constant_s:g} 1')
    return ET.tostring(tree, encoding='unicode')+'\n'


def make_controller(profile=None, variant='original'):
    from tools.control.fixed_admittance import FixedAdmittance, AdmittanceConfig
    from tools.control.reference_search import ReferenceSearchRecovery
    p = profile or NewtonProfile()
    changes = {'original': {}, 'exit_50um': dict(search_exit_advance_m=.00005),
               'coverage_180um': dict(spiral_radius_m=.00018, spiral_pitch_m=.00009)}
    if variant not in changes:
        raise ValueError('Unregistered N1 traditional variant')
    controller = ReferenceSearchRecovery(
        NewtonSearchConfig(search_force_N=p.search_force_N, force_guard_N=p.force_guard_N, **changes[variant]),
        NewtonRiskConfig(force_guard_N=p.force_guard_N), NewtonLoadConfig(force_guard_N=p.force_guard_N))
    controller.admittance = FixedAdmittance(AdmittanceConfig(
        virtual_mass=(20., 20., .02, .02), damping=(2000., 2000., 1., 1.)))
    return controller


class NewtonReward(EpisodeReward):
    def __init__(self, target_travel_m, profile=None):
        super().__init__(target_travel_m)
        self.profile = profile or NewtonProfile()

    def advance(self, *, advance_m, dt, force_N, torque_G_Nm):
        if not all(math.isfinite(v) and v >= 0 for v in (force_N, torque_G_Nm)):
            raise ValueError('Finite nonnegative cycle loads required')
        # Reuse maximum-progress and terminal accounting exactly; convert to the
        # old helper's dimensionless ratios without clipping raw measurements.
        return super().advance(advance_m=advance_m, dt=dt,
            force_N=force_N*.025/self.profile.force_guard_N,
            torque_G_Nm=torque_G_Nm*.0005/self.profile.torque_guard_Nm)


def normalize_wrench_history(history, profile=None):
    p = profile or NewtonProfile()
    values = np.asarray(history, dtype=float)
    if values.shape != (24,) or not np.isfinite(values).all():
        raise ValueError('Finite four-sample six-axis history required')
    scales = np.asarray(([p.force_guard_N]*3+[p.torque_guard_Nm]*3)*4)
    return np.clip(values/scales, -10, 10).astype(np.float32)


def environment_class():
    from tools.learning.guarded_environment import LearningEnvironment, GuardCandidateConfig
    from tools.dynamics.cartesian import CartesianEnvironment

    class NewtonEnvironment(LearningEnvironment):
        def __init__(self, profile=None):
            self.profile = profile or NewtonProfile()
            self.guard_config = GuardCandidateConfig(math.radians(2.5), math.radians(1.))
            self._observation_ready = False
            self._clear_facts()
            # Initialize the inherited sampler/guards with the separate drive.
            CartesianEnvironment.__init__(self, config=dynamic_config(self.profile), segments=256,
                                          model_xml=build_model_xml(self.profile))
            self.model.opt.ccd_tolerance = 1e-12

        def metadata(self):
            return {**super().metadata(), 'force_profile': self.profile.metadata()}
    return NewtonEnvironment


def session_class():
    from tools.learning.v4_continuation import ContinuationResidualSession
    from tools.learning.v4_observation import V4ObservationBuilder
    from tools.learning.layered_session import LayeredReferenceSession
    from tools.model.clearance_task import finish_criteria
    from tools.model.layered_task import layered_pin_fit

    class NewtonObservation(V4ObservationBuilder):
        version = 'residual_reference_whitelist_newton_N1_v1'

        def __init__(self, initial, config, profile):
            super().__init__(initial, config)
            self.profile = profile

        def capture(self, snapshot, context, *, refresh=False):
            vector, raw = super().capture(snapshot, context, refresh=refresh)
            vector[self.slices['wrench_history_M']] = normalize_wrench_history(raw['wrench_history_M'], self.profile)
            for field in self.schema:
                if field['name'] == 'wrench_history_M':
                    field['scale'] = ([self.profile.force_guard_N]*3+[self.profile.torque_guard_Nm]*3)*4
            return vector, raw

    class NewtonResidualSession(ContinuationResidualSession):
        def __init__(self, environment, *, variant='original', mode='F50'):
            self.profile = environment.profile
            criteria = {**finish_criteria(), 'force_N': self.profile.force_guard_N,
                        'torque_Nm': self.profile.torque_guard_Nm}
            super().__init__(environment=environment, mode=mode,
                controller_factory=lambda: make_controller(self.profile, variant),
                finish_criteria=criteria, geometry_checker=layered_pin_fit)

        def _reset_residual(self, case, seed):
            self._ready = self._features_ready = False
            self._cache = self._decorated_cache = None
            self.done = self.task_finished = True
            self.previous_residual = [0.]*4
            self.last_action_log = {}
            self.policy_raw = {}
            self.clipped_duration_s = 0.
            self.external_cut = False
            self.reward = NewtonReward(case.target_depth_m, self.profile)
            initial = LayeredReferenceSession.reset(self, case, seed)
            self.observations = NewtonObservation(initial.state, self.controller.config, self.profile)
            self._features_ready = True
            return self.prepare_cycle()
    return NewtonResidualSession
