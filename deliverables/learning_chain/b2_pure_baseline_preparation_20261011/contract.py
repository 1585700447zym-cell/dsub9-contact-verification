"""Four-case comparison and authorization contract; standard library only."""
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import importlib.metadata
import importlib.machinery
import json
import math
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
S20 = ROOT / 'deliverables/learning_chain/b2_joint_sac_continuation_execution_20261009'
HELPERS = ROOT / 'deliverables/learning_chain/b2_joint_sac_continuation_preparation_20261009'
SEED = 2026092716
LIMITS = dict(dynamic_episodes=4, environment_creations=4, resets=4,
              control_cycles=58000, native_steps=580000, per_episode_cycles=14500,
              per_episode_native_steps=145000, per_episode_wall_s=1200, whole_wall_s=7200,
              policy_calls=0, formal_updates=0, learner_constructions=0, tensor_loads=0,
              replay_publications=0, independent_tests=0)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''): h.update(chunk)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'),
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def helper(name):
    spec = importlib.util.spec_from_file_location('b2_fixed_' + name, HELPERS / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(HELPERS))
    try: spec.loader.exec_module(module)
    finally: sys.path.remove(str(HELPERS))
    return module


def write(path, value):
    helper('bounded_io').write(Path(path), value)


def now():
    return datetime.now(timezone(timedelta(hours=8))).isoformat()


def case_kwargs(point):
    expected = read(S20 / 'configuration.json')['cases']
    if canonical(point) not in {canonical(p) for p in expected}:
        raise ValueError('Only the four registered SCOPE20 poses are allowed')
    return dict(name=point['id'], x_offset_m=point['x_um'] * 1e-6,
                y_offset_m=point['y_um'] * 1e-6, roll_rad=math.radians(point['roll_deg']),
                pitch_rad=math.radians(point['pitch_deg']), start_origin_z_m=point['start_origin_z_m'],
                target_depth_m=point['target_depth_m'])


def check_pose(point, row):
    kw = case_kwargs(point)
    position = row['position_m']; quaternion = row['quaternion_wxyz']
    if len(position) != 3 or len(quaternion) != 4 or any(
            type(x) not in (int, float) or not math.isfinite(x) for x in position + quaternion):
        raise ValueError('Incomplete or nonfinite initial pose')
    roll = kw['roll_rad'] / 2; pitch = kw['pitch_rad'] / 2
    target = [math.cos(pitch) * math.cos(roll), math.cos(pitch) * math.sin(roll),
              math.sin(pitch) * math.cos(roll), -math.sin(pitch) * math.sin(roll)]
    xyz = [kw['x_offset_m'], kw['y_offset_m'], kw['start_origin_z_m']]
    if (max(abs(a - b) for a, b in zip(position, xyz)) > 1e-12 or
            min(max(abs(a - b) for a, b in zip(quaternion, target)),
                max(abs(a + b) for a, b in zip(quaternion, target))) > 1e-12):
        raise ValueError('Actual initial pose differs from registered joint pose')


def check_archive(raw, point, role, common_key, expected_score, schema):
    if role not in ('F0', 'F2000'): raise ValueError('Explicit learned evaluation role required')
    steps = 0 if role == 'F0' else 2000
    expected_stage = 'zero' if role == 'F0' else 'final'
    cases = read(S20 / 'configuration.json')['cases']
    if (raw['scope'] != 'frozen_development_evaluation' or raw['mode'] != 'F50' or
            raw['stage'] != expected_stage or raw['comparison_key'] != common_key or
            raw['case_id'] != point['id'] or raw['case_index'] != cases.index(point) or
            canonical(raw['case']) != canonical(point) or
            canonical(raw['simulation_case']) != canonical(case_kwargs(point)) or raw['seed'] != SEED or
            raw['optimizer_steps_start'] != steps or raw['optimizer_steps'] != steps or
            canonical(raw['observation_schema']) != canonical(schema)):
        raise ValueError('Archive task, case, schema or update identity differs')
    check_pose(point, raw['trace'][0])
    out = raw['outcome']
    if (raw['fault'] is not None or raw['reference_problems'] or raw['actual_reference_failed'] or
            out['simulation_valid'] is not True or out['physical_stopped'] is not True or
            any(out['guard_violations'].values())):
        raise ValueError('Existing evaluation is not valid/stopped/guard-clear')
    if (out['task_outcome'] != expected_score['task_outcome'] or
            abs(raw['task_end_time_s'] - expected_score['task_time_s']) > 1e-12 or
            any(abs(raw['peaks'][k] - expected_score['peaks'][k]) > 1e-12
                for k in ('force_N', 'torque_G_Nm'))):
        raise ValueError('Archive disagrees with accepted SCOPE20 score')
    policy = raw['policy_sha256']
    if not isinstance(policy, str) or len(policy) != 64: raise ValueError('Policy identity missing')
    return dict(case_id=point['id'], role=role, task_outcome=out['task_outcome'],
                task_time_s=raw['task_end_time_s'], force_N=raw['peaks']['force_N'],
                torque_G_Nm=raw['peaks']['torque_G_Nm'], policy_sha256=policy,
                historical_model_scope_qualified=raw['source_session_outcome']['model_scope_qualified'],
                historical_training_admitted=raw['source_session_outcome']['training_admitted'],
                reused_as='development_comparison_only')


def next_case(entries, cases):
    if len(entries) > 4 or len(cases) != 4: raise ValueError('Four-attempt ceiling exceeded')
    for index, entry in enumerate(entries):
        if entry['case_id'] != cases[index]['id']: raise ValueError('Duplicate or reordered case')
        if entry.get('status') != 'finished': raise ValueError('Incomplete attempt cannot be retried')
        out = entry['outcome']
        if (entry.get('healthy') is not True or out['simulation_valid'] is not True or
                out['physical_stopped'] is not True or any(out['guard_violations'].values()) or
                out['task_outcome'] not in ('FULL_SUCCESS', 'TASK_FAILURE')):
            return None
    return cases[len(entries)] if len(entries) < 4 else None


def grant_template(binding_pin, run_id):
    return dict(version='b2_pure_baseline_grant_v1', binding_sha256=binding_pin, run_id=run_id,
                explicit_user_authorized=False, human_evidence='', status='DRAFT', limits=dict(LIMITS),
                cumulative_before=254, old_budget_closed=True, retries=0, purpose='four_pure_B2_development')


def require_grant(grant, binding_pin, run_id):
    expected = grant_template(binding_pin, run_id)
    if (set(grant) != set(expected) or grant.get('version') != expected['version'] or
            grant.get('binding_sha256') != binding_pin or grant.get('run_id') != run_id or
            grant.get('explicit_user_authorized') is not True or grant.get('status') != 'OPEN' or
            not isinstance(grant.get('human_evidence'), str) or not grant['human_evidence'].strip() or
            any(canonical(grant[k]) != canonical(expected[k]) for k in
                ('limits', 'cumulative_before', 'old_budget_closed', 'retries', 'purpose')) or
            not isinstance(run_id, str) or not run_id or run_id == 'pending-new-run-id'):
        raise PermissionError('A separately bound explicit four-B2 grant is required before scientific imports')


def check_runtime(runtime, *, check_interpreter=False):
    """Read package metadata and file inventory without importing numerical code."""
    site = Path(runtime['site_packages'])
    normal = lambda name: name.lower().replace('-', '_').replace('.', '_')
    actual = {}
    for dist in importlib.metadata.distributions(path=[str(site)]):
        key = normal(dist.metadata['Name'])
        if key in actual: raise ValueError('Duplicate runtime package metadata: ' + key)
        actual[key] = dist.version
    for name, version in runtime['versions'].items():
        if actual.get(normal(name)) != version: raise ValueError('Runtime package version differs: ' + name)
    for path, expected in runtime['inventories'].items():
        folder = Path(path)
        actual_files = sorted(str(p.relative_to(folder)).replace('\\', '/') for p in folder.rglob('*')
                              if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc')
        if actual_files != sorted(expected): raise ValueError('Numerical package inventory differs: ' + path)
    for name, path in runtime['package_paths'].items():
        spec = importlib.machinery.PathFinder.find_spec(name, [str(site)])
        if spec is None or spec.origin is None or Path(spec.origin).resolve() != Path(path).resolve():
            raise ValueError('Numerical package origin differs: ' + name)
    if check_interpreter and (not sys.flags.isolated or
            Path(sys.executable).resolve() != Path(runtime['executable']).resolve() or
            Path(sys._base_executable).resolve() != Path(runtime['base_executable']).resolve() or
            Path(sys.prefix).resolve() != Path(runtime['prefix']).resolve() or
            '.'.join(map(str, sys.version_info[:3])) != runtime['python']):
        raise PermissionError('Frozen isolated numerical interpreter required')


def verify_binding():
    binding = read(OUT / 'source_binding.json')
    for path, pin in binding['files'].items():
        if sha(Path(path)) != pin: raise ValueError('Bound source changed: ' + path)
    check_runtime(binding['numerical_runtime'])
    config = read(OUT / 'configuration.json')
    original = read(S20 / 'configuration.json')
    if canonical(config) != canonical(original): raise ValueError('Common task drift')
    return binding, config
