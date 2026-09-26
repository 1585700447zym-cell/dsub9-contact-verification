"""Fail-closed B.1 evidence binding. Not a collector, trainer or safety certificate.

Records must be pinned by a trusted delivery digest. Hashes detect stale inputs,
not a malicious local author who can replace the code and its trust anchor.
"""
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

REQUIRED_GATES = ('runtime', 'config', 'scope', 'historical_evidence', 'tests', 'cost', 'source_unchanged')


def short_training_config():
    return dict(version='engineering_short_train_v1', scope='engineering_chain_only',
        physics=dict(backend='native', segments=256, ccd_tolerance=1e-12,
                     timestep_s=.0002, control_period_s=.002, policy_period_s=.002),
        guard=dict(max_rotation_from_start_rad=math.radians(2.5),
                   initial_roll_pitch_limit_rad=math.radians(1.5)),
        domain=dict(distribution='independent_uniform_XY', x_limit_m=50e-6, y_limit_m=50e-6,
                    roll_rad=0., pitch_rad=0., start_origin_z_m=-.004, target_depth_m=.004),
        action=dict(scale=[.00015, .00015, .005, .005], enabled_stages=['INSERT', 'SEARCH']),
        sampling=dict(target_cycles=20000, stop_at='whole_episode_audited', watchdog_cycles=13000,
                      workers=1, seed=2026092609, rng='PCG64', initial_resampling=False),
        learning=dict(learning_rate=.0003, batch_size=256, warmup_audited_transitions=5000,
            replay_capacity=100000, gradient_batches_per_audited_transition=.25,
            max_gradient_batches=8250, discount_time_constant_s=10.,
            gamma_nominal=math.exp(-.002/10), discount='exp(-actual_dt_s/10)',
            entropy_initial=.01, target_entropy=-4., entropy_learned=True,
            tau=.005, network=[256, 256], activation='ReLU', seed=2026092609,
            device='cpu', torch_threads=1, replay_publish='whole_episode_after_audit',
            permission_masks='tensor_masks_v3', reward='contract_v3_unchanged'),
        versions={'python': '3.13.5', 'mujoco': '3.13.0', 'torch': '2.12.1+cpu',
                  'numpy': '2.1.3', 'gymnasium': '1.2.3', 'stable-baselines3': '2.8.0'})


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def validate_config(config):
    # Strict canonical comparison also distinguishes True from 1 and rejects NaN.
    if canonical(config) != canonical(short_training_config()):
        raise ValueError('Config is not the explicit engineering_short_train_v1 configuration')


def validate_case(case):
    fields = ('x_offset_m', 'y_offset_m', 'roll_rad', 'pitch_rad', 'start_origin_z_m', 'target_depth_m')
    for name in fields:
        value = case.get(name)
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError(f'Invalid case field: {name}')
    if (abs(case['x_offset_m']) > 50e-6 or abs(case['y_offset_m']) > 50e-6 or
            case['roll_rad'] != 0 or case['pitch_rad'] != 0 or
            case['start_origin_z_m'] != -.004 or case['target_depth_m'] != .004):
        raise ValueError('Case outside engineering initial distribution')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class InputBinding:
    """Read once: validation and archival consume exactly the same bytes."""
    def __init__(self, paths):
        self.contents = {Path(p).resolve(): Path(p).read_bytes() for p in paths}

    def json(self, path):
        return json.loads(self.contents[Path(path).resolve()].decode('utf-8'))

    def verify_unchanged(self):
        for path, content in self.contents.items():
            if not path.is_file() or path.read_bytes() != content:
                raise ValueError(f'Input changed while checking: {path}')

    def copy_to(self, source, destination):
        Path(destination).write_bytes(self.contents[Path(source).resolve()])


def validate_timings(values, *, expected_count):
    if (type(expected_count) is not int or expected_count < 1 or
            not isinstance(values, list) or len(values) != expected_count or
            any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in values)):
        raise ValueError('Timing samples must be complete, positive and finite')


def local_file(root, name):
    root = Path(root).resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError(f'Path outside root: {name}')
    return path


def verify_files(root, files):
    if not isinstance(files, dict) or not files:
        raise ValueError('Nonempty fingerprint map required')
    for name, expected in files.items():
        path = local_file(root, name)
        if not path.is_file() or digest(path) != expected:
            raise ValueError(f'Fingerprint missing/changed: {name}')
    return len(files)


def verify_test_report(path, *, required_modules, minimum):
    report = ET.parse(path).getroot()
    if any(next(report.iter(tag), None) is not None for tag in ('failure', 'error', 'skipped')):
        raise ValueError('Failed, errored or skipped tests cannot qualify')
    cases = list(report.iter('testcase'))
    ids = [(c.get('classname'), c.get('name')) for c in cases]
    modules = {str(c.get('classname')).split('.')[-1] for c in cases}
    if (len(cases) < minimum or len(set(ids)) != len(ids) or
            any(not all(pair) for pair in ids) or not set(required_modules) <= modules):
        raise ValueError('Empty, duplicate or incomplete test coverage')
    return dict(passed=len(cases), modules=sorted(modules), sha256=digest(path))


def verify_admission(path, *, root, expected_digest, config, runtime, current_sources):
    if not expected_digest or digest(path) != expected_digest:
        raise ValueError('Admission record does not match trusted delivery digest')
    record = json.loads(Path(path).read_text(encoding='utf-8'))
    validate_config(config)
    if (record.get('version') != 'b1_admission_v1' or record.get('training_admitted') is not True or
            record.get('scope') != 'engineering_chain_only' or
            set(record.get('gates', {})) != set(REQUIRED_GATES) or
            any(v is not True for v in record['gates'].values()) or
            canonical(record.get('config')) != canonical(config) or
            canonical(record.get('runtime')) != canonical(runtime) or
            record.get('source_sha256') != current_sources):
        raise ValueError('Admission incomplete, stale or out of scope')
    verify_files(root, record['source_sha256'])
    verify_files(root, record['evidence_sha256'])
    return record


def project_budget(*, cycle_s, network_batch_s, init_s, audit_s):
    values = (cycle_s, network_batch_s, init_s, audit_s)
    if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in values):
        raise ValueError('Positive finite measured costs required')
    c = short_training_config()
    cap = c['sampling']['target_cycles'] + c['sampling']['watchdog_cycles']
    batches = math.ceil(cap * c['learning']['gradient_batches_per_audited_transition'])
    # No minimum episode length is assumed: at most one reset/audit per cycle.
    # Useful forecast is reported per episode separately; no false tight bound.
    return dict(projected_cycles_cap=cap, gradient_batches_cap=batches,
        sampling_seconds=cap*cycle_s, network_proxy_seconds=batches*network_batch_s,
        reset_audit_seconds_per_episode=init_s+audit_s,
        forecast_formula='sampling_seconds + network_proxy_seconds + episodes * reset_audit_seconds_per_episode',
        recommended_wall_budget_s=3600, actual_training_measured=False,
        limitation='Network backward proxy, not optimizer/replay/IO training time or a guaranteed upper bound. Stop requested at budget; complete current safe audit.')
