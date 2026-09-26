"""Versioned policy whitelist. No MuJoCo, case labels or hole truth are inputs.

Only capture() advances the four CONTROL-sample wrench history, once per cycle.
The 6ms history plus explicit controller summaries do not claim full Markov state.
"""
from copy import deepcopy
import math
import numpy as np

POLICY_PHASES = ('INSERT', 'UNLOAD', 'SEARCH', 'WAIT_RECOVERY', 'FAILED')
PHYSICAL_PHASES = ('RUNNING', 'STOPPING', 'RETRACT', 'TERMINAL')
RECOVERY_PHASES = (None, 'WAIT_STOP', 'RETRACT', 'WAIT_RESUME')
DECISIONS = (None, 'TARGET_PLANE_REACHED', 'GEOMETRIC_SUCCESS', 'TARGET_POSE_NOT_SETTLED',
             'TIME_LIMIT', 'CONTACT_GUARD', 'MOTION_VIOLATION', 'EXTERNAL_TRUNCATION', 'OTHER')
GUARDS = ('FORCE_LIMIT', 'TORQUE_LIMIT', 'PENETRATION_LIMIT', 'SPEED_LIMIT',
          'ANGULAR_SPEED_LIMIT', 'TRAVEL_LIMIT', 'ROTATION_LIMIT')
VECTOR_WIDTHS = dict(wrench_history_M=24, relative_position_m=3, relative_rotation_world_rad=3,
    velocity_world=6, base_command=6, previous_limited_command=6, previous_residual=4,
    policy_phase=5, physical_phase=4, recovery_phase=4, decision=9, latched_guards=7,
    admittance_velocity=4, admittance_offset=4, search_origin_m=3,
    reference_position_error_m=3, reference_rotation_error_world_rad=3)


def rotation_vector_world(initial, current):
    values = []
    for q in (initial, current):
        q = np.asarray(q, dtype=float)
        if q.shape != (4,) or not np.isfinite(q).all() or not np.any(q):
            raise ValueError('Finite nonzero shape4 quaternion required')
        q = q / np.max(np.abs(q))
        values.append(q / np.linalg.norm(q))
    a, b = values
    w = float(np.dot(a, b))
    v = a[0]*b[1:] - b[0]*a[1:] + np.cross(a[1:], b[1:])
    if w < 0 or (w == 0 and next((x for x in v if x != 0), 1) < 0):
        w, v = -w, -v
    length = float(np.linalg.norm(v))
    return np.zeros(3) if length < 1e-15 else v * (2*math.atan2(length, w)/length)


class ObservationBuilder:
    version = 'residual_whitelist_v1'

    def __init__(self, initial_state, config):
        self.initial_position = np.array(initial_state['position_m'], dtype=float)
        self.initial_quaternion = np.array(initial_state['quaternion_wxyz'], dtype=float)
        self.config = config
        self._history = [list(initial_state['contact_wrench_M']) for _ in range(4)]
        self._maximum = 0.
        self._cycle = None
        self._cached = None
        self.slices = {}
        self.schema = []

    def capture(self, snapshot, context, *, refresh=False):
        same_cycle = snapshot.cycle_id == self._cycle
        if same_cycle and not refresh:
            return deepcopy(self._cached)
        if self._cycle is not None and not same_cycle and snapshot.cycle_id != self._cycle + 1:
            raise ValueError('Observation history requires consecutive control cycles')
        row, ctrl, cfg, now = snapshot.state, snapshot.controller_state, self.config, snapshot.time_s
        for value in (ctrl['search_count'], context['recovery_count']):
            if np.asarray(value).shape != () or not np.isfinite(value):
                raise ValueError('Finite scalar controller count required')
        times = [now, ctrl['phase_start']] + [entry[0] for entry in ctrl['history']]
        times += [context[key] for key in ('hold_start', 'wait_start', 'actual_stop_start') if context[key] is not None]
        if not np.isfinite(times).all():
            raise ValueError('Nonfinite source timer; do not clamp to a valid zero')
        history = self._history if self._cycle is None or same_cycle else [row['contact_wrench_M']] + self._history[:3]
        displacement = np.asarray(row['position_m']) - self.initial_position
        maximum = max(self._maximum, max(0., float(displacement[2])))
        raw, vector, schema, slices = {}, [], [], {}

        def add(name, value, scale=1., unit='1', source='controller'):
            array = np.asarray(value, dtype=float)
            expected_shape = (VECTOR_WIDTHS[name],) if name in VECTOR_WIDTHS else ()
            if array.shape != expected_shape:
                raise ValueError(f'Invalid policy field shape: {name}: {array.shape}')
            values = np.atleast_1d(array)
            scales = np.broadcast_to(np.asarray(scale, dtype=float), values.shape)
            if not np.isfinite(values).all() or not np.isfinite(scales).all() or np.any(scales <= 0):
                raise ValueError(f'Invalid policy field: {name}')
            raw[name] = values.tolist()
            start = len(vector)
            vector.extend(np.clip(values/scales, -10, 10).tolist())
            slices[name] = slice(start, len(vector))
            schema.append(dict(name=name, start=start, width=len(values), scale=scales.tolist(), unit=unit, source=source))

        def onehot(name, value, options):
            if value not in options:
                raise ValueError(f'Unrecognized {name}: {value}')
            add(name, [value == option for option in options])

        def timer(name, start, budget):
            add(name + '_elapsed_s', 0. if start is None else max(0., now-start), budget, 's')
            add(name + '_valid', start is not None)

        add('wrench_history_M', np.asarray(history).reshape(-1), ([.025]*3 + [.0005]*3)*4,
            'N,Nm', 'simulation_contact_wrench_M_control_samples_newest_first')
        add('relative_position_m', displacement, .004, 'm', 'relative_proprioception')
        add('relative_rotation_world_rad', rotation_vector_world(self.initial_quaternion, row['quaternion_wxyz']), .08, 'rad', 'relative_proprioception')
        add('velocity_world', row['velocity_world'], [.001]*3+[.03]*3, 'm/s,rad/s', 'proprioception')
        add('maximum_advance_m', maximum, .004, 'm', 'relative_proprioception')
        add('base_command', snapshot.base_command, [.001]*3+[.03]*3, 'm/s,rad/s')
        add('previous_limited_command', row['limited_command_world'], [.001]*3+[.03]*3, 'm/s,rad/s')
        add('previous_residual', context['previous_residual'], [.001]*2+[.03]*2, 'm/s,rad/s')
        onehot('policy_phase', ctrl['phase'], POLICY_PHASES)
        onehot('physical_phase', row['phase'], PHYSICAL_PHASES)
        onehot('recovery_phase', context['recovery_state'], RECOVERY_PHASES)
        reason = context['reason']
        onehot('decision', reason if reason in DECISIONS else 'OTHER', DECISIONS)
        add('pending', reason is not None)
        add('action_active', snapshot.residual_enabled)
        facts = context['guard_facts']
        add('simulation_valid', facts['simulation_valid'])
        reasons = facts['contact_reasons'] + facts['motion_reasons']
        add('latched_guards', [reason in reasons for reason in GUARDS])
        add('invalid_latched', bool(facts['invalid_reasons']))
        add('total_budget_remaining_s', max(0., cfg.total_action_time_s-now), cfg.total_action_time_s, 's')
        search_active = ctrl['phase'] == 'SEARCH'
        add('search_budget_remaining_s', max(0., cfg.search_time_s-(now-ctrl['phase_start'])) if search_active else 0., cfg.search_time_s, 's')
        add('search_budget_valid', search_active)
        add('searches_remaining', max(0, cfg.max_searches-ctrl['search_count']), cfg.max_searches)
        add('recoveries_remaining', max(0, 1-context['recovery_count']))
        add('admittance_velocity', ctrl['admittance_velocity'], [.001]*2+[.03]*2, 'm/s,rad/s')
        add('admittance_offset', ctrl['admittance_offset'], [.004]*2+[.08]*2, 'm,rad')
        add('spiral_theta_rad', ctrl['theta'], 2*math.pi*cfg.spiral_radius_m/cfg.spiral_pitch_m, 'rad')
        origin = ctrl['search_origin']  # Already expressed relative to episode start by B2.
        add('search_origin_m', [0.]*3 if origin is None else origin, .004, 'm')
        add('search_origin_valid', origin is not None)
        old = ctrl['history'][0] if ctrl['history'] else None
        add('stall_progress_m', 0. if old is None else displacement[2]-old[1], .004, 'm')
        add('stall_span_s', 0. if old is None else max(0., now-old[0]), cfg.stall_window_s, 's')
        add('stall_valid', old is not None and now > old[0])
        add('phase_elapsed_s', max(0., now-ctrl['phase_start']), cfg.total_action_time_s, 's')
        timer('hold', context['hold_start'], .1)
        timer('stop', context['actual_stop_start'], 2.)
        timer('wait', context['wait_start'], cfg.wait_stable_s)
        reference = row['reference_qpos']
        add('reference_position_error_m', np.asarray(reference[:3])-row['position_m'], .004, 'm')
        add('reference_rotation_error_world_rad', rotation_vector_world(row['quaternion_wxyz'], reference[3:]), .08, 'rad')
        self._history = deepcopy(history)
        self._maximum, self._cycle = maximum, snapshot.cycle_id
        self.schema, self.slices = schema, slices
        self._cached = (np.asarray(vector, dtype=np.float32), raw)
        return deepcopy(self._cached)
