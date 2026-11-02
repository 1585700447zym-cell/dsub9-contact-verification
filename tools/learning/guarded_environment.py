"""Candidate v3 common guards; NOT a qualified training environment.

The frozen integrator/drive are inherited unchanged. Finite guard violations
request a physical stop; numerical invalidity remains a separate latched fact.
This module supplies no model-domain qualification or training permission.
"""
from copy import deepcopy
from dataclasses import asdict, dataclass
import math
import numpy as np

from .environment import SampledCompatibilityEnvironment


@dataclass(frozen=True)
class GuardCandidateConfig:
    max_rotation_from_start_rad: float
    initial_roll_pitch_limit_rad: float

    def __post_init__(self):
        for value in asdict(self).values():
            if isinstance(value, bool) or not math.isfinite(value) or not 0 < value <= math.pi:
                raise ValueError('Guard angles must be explicitly finite in (0, pi]')


def relative_rotation_rad(initial, current):
    """Shortest relative SO(3) angle, invariant under quaternion sign.

    atan2 is well conditioned near zero; normalization is overflow-safe.
    """
    quats = []
    for value in (initial, current):
        q = np.asarray(value, dtype=float)
        if q.shape != (4,) or not np.isfinite(q).all() or not np.any(q):
            raise ValueError('Rotation requires finite nonzero shape4 quaternions')
        q = q / np.max(np.abs(q))
        quats.append(q / np.linalg.norm(q))
    a, b = quats
    scalar = float(np.dot(a, b))
    vector = a[0] * b[1:] - b[0] * a[1:] - np.cross(a[1:], b[1:])
    return 2 * math.atan2(float(np.linalg.norm(vector)), abs(scalar))


class LearningEnvironment(SampledCompatibilityEnvironment):
    def __init__(self, *, guard_config: GuardCandidateConfig, model_xml=None):
        if not isinstance(guard_config, GuardCandidateConfig):
            raise TypeError('Explicit GuardCandidateConfig required')
        self.guard_config = guard_config
        self._observation_ready = False
        self._clear_facts()
        super().__init__(model_xml=model_xml)

    def _clear_facts(self):
        self._facts = dict(simulation_valid=True, invalid_reasons=[], contact_reasons=[],
                           motion_reasons=[], max_rotation_from_start_rad=0., checked_substeps=0)

    @property
    def guard_facts(self):
        return deepcopy(self._facts)

    def reset(self, case, *, allow_initial_contact=False):
        self._clear_facts()
        self._observation_ready = False
        self.phase = 'TERMINAL'  # Failed reset must close the preceding episode.
        self.events = []
        self.stop_samples = []
        self.peaks = {}
        self.physical_steps = 0
        self.stop_snapshot = None
        self.begin_cycle()
        values = [case.roll_rad, case.pitch_rad]
        if (not np.isfinite(values).all() or
                max(abs(v) for v in values) > self.guard_config.initial_roll_pitch_limit_rad):
            self._facts['simulation_valid'] = False
            self._facts['invalid_reasons'].append('INITIAL_ORIENTATION_OUTSIDE_CANDIDATE')
            raise ValueError('Initial orientation outside candidate range')
        try:
            row = super().reset(case, allow_initial_contact=allow_initial_contact)
            self._observation_ready = True
            return row
        except Exception:
            self.phase = 'TERMINAL'
            self._facts['simulation_valid'] = False
            if 'INVALID_INITIAL_STATE' not in self._facts['invalid_reasons']:
                self._facts['invalid_reasons'].append('INVALID_INITIAL_STATE')
            raise

    def observe(self):
        if not self._observation_ready:
            raise RuntimeError('No observation from a successfully initialized episode')
        return super().observe()

    def _collect(self, row, *, engine_valid):
        """Collect independent facts before choosing a response, even if invalid."""
        c = self.config
        found = dict(invalid_reasons=[], contact_reasons=[], motion_reasons=[])
        if not engine_valid:
            found['invalid_reasons'].append('INVALID_SIMULATION')
        fields = ('position_m', 'velocity_world', 'contact_wrench_M',
                  'contact_wrench_G', 'penetration_m', 'quaternion_wxyz')
        if not all(np.isfinite(row[key]).all() for key in fields):
            found['invalid_reasons'].append('NONFINITE_OBSERVATION')
        penetration = row['penetration_m']
        if np.isfinite(penetration) and penetration > c.invalid_penetration_m:
            found['invalid_reasons'].append('INVALID_PENETRATION')
        checks = [
            ('contact_reasons', 'PENETRATION_LIMIT', penetration, c.stop_penetration_m),
            ('contact_reasons', 'FORCE_LIMIT', np.linalg.norm(row['contact_wrench_M'][:3]), c.stop_force_N),
            ('contact_reasons', 'TORQUE_LIMIT', np.linalg.norm(row['contact_wrench_G'][3:]), c.stop_torque_Nm),
            ('motion_reasons', 'SPEED_LIMIT', np.linalg.norm(row['velocity_world'][:3]), c.actual_speed_limit),
            ('motion_reasons', 'ANGULAR_SPEED_LIMIT', np.linalg.norm(row['velocity_world'][3:]), c.actual_angular_speed_limit),
            ('motion_reasons', 'TRAVEL_LIMIT', np.linalg.norm(np.array(row['position_m']) - self.initial[:3]), c.travel_limit_m),
        ]
        try:
            angle = relative_rotation_rad(self.initial[3:], row['quaternion_wxyz'])
            self._facts['max_rotation_from_start_rad'] = max(self._facts['max_rotation_from_start_rad'], angle)
            checks.append(('motion_reasons', 'ROTATION_LIMIT', angle, self.guard_config.max_rotation_from_start_rad))
        except ValueError:
            found['invalid_reasons'].append('INVALID_QUATERNION')
        for group, reason, value, limit in checks:
            if np.isfinite(value) and value > limit:
                found[group].append(reason)
        new = []
        for group, reasons in found.items():
            for reason in reasons:
                if reason not in self._facts[group]:
                    self._facts[group].append(reason)
                    new.append(reason)
        if self._facts['invalid_reasons']:
            self._facts['simulation_valid'] = False
        return found, new

    def _guard(self, row):
        self._facts['checked_substeps'] += 1
        found, new = self._collect(row, engine_valid=self._state_valid())
        if found['invalid_reasons']:
            self._terminate('+'.join(found['invalid_reasons']))
        elif found['contact_reasons'] or found['motion_reasons']:
            reasons = found['contact_reasons'] + found['motion_reasons']
            if self.phase != 'STOPPING':
                self.stop('+'.join(reasons))
            elif new:
                self.events.append(dict(time_s=float(self.data.time), reason='+'.join(new), phase='STOPPING'))

    def _terminate(self, reason):
        # The inherited loop may reject a warning/NaN/command BEFORE _guard.
        # Retain other measurable facts; never reuse last_finite as current truth.
        self._facts['simulation_valid'] = False
        if reason not in self._facts['invalid_reasons']:
            self._facts['invalid_reasons'].append(reason)
        if hasattr(self, 'initial'):
            try:
                self._collect(self._read(), engine_valid=False)
            except (ValueError, FloatingPointError):
                pass  # Invalid engine buffers cannot always supply a usable row.
        super()._terminate(reason)

    def request_recovery(self):
        if (not self._facts['simulation_valid'] or self._facts['contact_reasons'] or
                self._facts['motion_reasons']):
            raise RuntimeError('Latched candidate guard forbids recovery')
        return super().request_recovery()

    def metadata(self):
        return {**super().metadata(), 'common_guard_version': 'v3_candidate_1',
                'guard_config': asdict(self.guard_config), 'training_admitted': False,
                'model_scope_qualified': False}
