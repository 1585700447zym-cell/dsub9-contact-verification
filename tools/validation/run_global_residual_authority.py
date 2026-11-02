"""Register, then explicitly launch four one-shot 30 s residual-authority trials.

Import and --prepare never construct a model/environment or load a checkpoint.
--run/--launch are separate execution requests; no retry, resume or automation.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import gzip
import importlib.abc
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'deliverables/learning_chain/global_residual_authority_20261028'
PYTHON = ROOT / 'tmp/learning_cpu_20260924/Scripts/python.exe'
RUNTIME = ROOT / 'deliverables/learning_chain/b2_repaired_cycle_v2_20260928/runtime.json'
ORIGINAL = ROOT / 'deliverables/learning_chain/five_axis_pretraining_20261023/registration.json'
PREVIOUS = ROOT / 'deliverables/learning_chain/five_axis_entropy_closed_loop_20261026'
POSTMORTEM = ROOT / 'deliverables/learning_chain/five_axis_entropy_postmortem_20261027'
PLAN = ROOT / 'docs/superpowers/plans/2026-10-28-global-residual-30s.md'
COMMON = ('dynamic_config', 'effective_kd', 'model_xml_sha256', 'actual_model', 'runtime')
MAX_CYCLES = 16000
SEED = 2026092716
CUMULATIVE_BEFORE = 415

# These helpers have no environment, model, neural or optimizer imports.
from tools.validation.run_yaw_pilot import (read, sha, write, publish_archive,
    actual_common, model_archive_bytes, supervise)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def schedule():
    jobs = []
    for name, angle in [('YAW_P15', 1.5), ('YAW_M15', -1.5)]:
        point = dict(name=name, x_offset_m=.0003, y_offset_m=.0003,
            roll_rad=math.radians(-1.), pitch_rad=math.radians(1.), yaw_rad=math.radians(angle),
            start_origin_z_m=-.005, target_depth_m=.005)
        jobs.extend(dict(id=f'{profile}_{name}', profile=profile, case=dict(point)) for profile in ('G0', 'G1'))
    return jobs


def script_contract():
    return dict(version='first_search_six_trapezoids_2ms_v1', period_s=.002,
        first_search_delay_s=.2, pulse_order=['+yaw', '-yaw', '+X', '-X', '+Y', '-Y'],
        ramp_up_s=.2, hold_s=.6, ramp_down_s=.2, gap_s=.2,
        interpolation='piecewise_linear_at_cycle_start',
        interruption='cancel_all_remaining_on_search_exit_or_permission_loss; never_resume',
        uses_case_or_pin_truth=False, action_hold_cycles=1)


class DiagnosticScript:
    """Cycle-indexed normalized requests; every cycle, including disabled, is seen."""
    def __init__(self):
        self.first_search_cycle = None
        self.last_cycle = -1
        self.status = 'waiting'
        self.cancellation_reason = None

    def select(self, cycle, phase, enabled):
        if type(cycle) is not int or cycle < 0 or cycle < self.last_cycle:
            raise ValueError('Nondecreasing nonnegative control cycle required')
        self.last_cycle = cycle
        zero = [0.] * 5
        if self.status in ('cancelled', 'completed'):
            return zero
        if self.first_search_cycle is None:
            if phase != 'SEARCH':
                return zero
            self.first_search_cycle = cycle
            self.status = 'running'
        if phase != 'SEARCH' or not enabled:
            self.status = 'cancelled'
            self.cancellation_reason = 'SEARCH_EXIT' if phase != 'SEARCH' else 'RESIDUAL_PERMISSION_INTERRUPTED'
            return zero
        elapsed = cycle - self.first_search_cycle - 100
        if elapsed < 0:
            return zero
        if elapsed >= 3500:
            self.status = 'completed'
            return zero
        segment, part = divmod(elapsed, 600)
        if part >= 500:
            return zero
        axis, sign = [(4, 1.), (4, -1.), (0, 1.), (0, -1.), (1, 1.), (1, -1.)][segment]
        gain = min(part / 100., 1., (500 - part) / 100.)
        zero[axis] = sign * gain
        return zero

    def state(self):
        return dict(status=self.status, first_search_cycle=self.first_search_cycle,
            last_cycle=self.last_cycle, cancellation_reason=self.cancellation_reason)


class NoLearning(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in ('torch', 'stable_baselines3', 'tensorflow', 'jax', 'keras'):
            raise PermissionError('Global residual engineering trials forbid neural/optimizer imports')


def verify_inputs(pins, *, root=ROOT):
    root = Path(root).resolve()
    for name, digest in pins.items():
        target = (root / name).resolve()
        if not target.is_relative_to(root) or sha(target) != digest:
            raise ValueError('Frozen source/evidence changed: ' + name)


def freeze_sources(paths, folder):
    pins = {}
    for path in sorted(set(map(Path, paths))):
        name = path.relative_to(ROOT).as_posix()
        target = Path(folder) / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
        pins[name] = sha(path)
    return pins


def previous_evidence():
    closeout = read(PREVIOUS / 'completion_verification.json')
    proof = read(POSTMORTEM / 'verification.json')
    if (not closeout.get('verified') or not proof.get('verified')
            or proof.get('cost', {}).get('cumulative_initializations') != CUMULATIVE_BEFORE
            or proof['prior_completion_verification_sha256'] != sha(PREVIOUS / 'completion_verification.json')):
        raise ValueError('Verified paired postmortem and cumulative-415 boundary required')
    for name, digest in proof['original_evidence_checked'].items():
        if sha(ROOT / name) != digest:
            raise ValueError('Previous paired evidence changed: ' + name)
    for name, digest in proof['artifacts'].items():
        if sha(POSTMORTEM / name) != digest:
            raise ValueError('Previous postmortem artifact changed: ' + name)
    return [ROOT / name for name in proof['original_evidence_checked']] + [
        POSTMORTEM / name for name in proof['artifacts']] + [
        PREVIOUS / 'completion_verification.json', POSTMORTEM / 'verification.json']


def implementation_sources():
    import xml.etree.ElementTree as ET
    xmls = list((ROOT / 'models').rglob('*.xml'))
    assets = []
    for path in xmls:
        for mesh in ET.parse(path).getroot().iter('mesh'):
            if mesh.get('file'):
                assets.append(ROOT / 'assets' / mesh.get('file'))
    return list((ROOT / 'tools').rglob('*.py')) + xmls + assets + [
        ROOT / 'deliverables/learning_chain/b2_newton_sac_preparation_20261016/newton_raw_audit.py',
        ROOT / 'deliverables/b2_search_recovery/matrix_v1_7cases/results_index.json',
        ROOT / 'tests/test_global_residual_authority.py', ROOT / 'tests/test_global_residual_runner.py',
        PLAN, RUNTIME, ORIGINAL, PYTHON]


def prepare():
    """Freeze current implementation and old evidence, without runtime selection."""
    from tools.learning.global_residual_action import profile_config
    old_evidence = previous_evidence()
    old = read(ORIGINAL)
    paths = implementation_sources() + old_evidence
    # Ensure all expected files are readable before claiming this destination.
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(path)
    OUT.mkdir()  # Never overwrite a previous or partial registration.
    pins = freeze_sources(paths, OUT / 'source_snapshot')
    reg = dict(version='global_residual_authority_30s_v1', inputs=pins,
        common=old['common'], profiles={profile: profile_config(profile) for profile in ('G0', 'G1')},
        schedule=schedule(), script=script_contract(), seed=SEED,
        task_deadline_s=30., stop_tail_s=2., max_control_cycles=MAX_CYCLES,
        max_physical_substeps_per_run=160000, max_physical_substeps=640000,
        max_initializations=4, cumulative_before=CUMULATIVE_BEFORE, retries=0,
        max_worker_wall_s=3600, max_parallel_workers=2, pair_audit_before_next=True,
        runtime_sha256=sha(RUNTIME), parent_registration_sha256=sha(ORIGINAL),
        previous_postmortem_sha256=sha(POSTMORTEM / 'verification.json'),
        neural_policy_calls=0, training_updates=0, replay_publications=0, final_test_episodes=0,
        learning_admitted=False, observation_width=140, action_dim=5,
        controls='Existing N2/450 search, admittance, phase logic, guards, stop and nine-pin success; shared 30s task',
        authorization='2026-10-28 global residual authority G0/G1 and common 30-second engineering comparison',
        prepared_only=True)
    write(OUT / 'registration.json', reg)
    print(json.dumps(dict(prepared=True, jobs=4, physical_initializations=0,
        physical_substeps=0, source_files=len(pins), learning_admitted=False)), flush=True)


def validate(reg):
    from tools.learning.global_residual_action import profile_config
    expected = dict(version='global_residual_authority_30s_v1',
        task_deadline_s=30., stop_tail_s=2., max_control_cycles=16000,
        max_physical_substeps_per_run=160000, max_physical_substeps=640000,
        max_initializations=4, cumulative_before=415, retries=0, max_parallel_workers=2,
        pair_audit_before_next=True, neural_policy_calls=0, training_updates=0,
        replay_publications=0, final_test_episodes=0, learning_admitted=False,
        observation_width=140, action_dim=5, seed=SEED, max_worker_wall_s=3600)
    if (any(reg.get(key) != value for key, value in expected.items())
            or reg['schedule'] != schedule() or reg['script'] != script_contract()
            or reg['profiles'] != {profile: profile_config(profile) for profile in ('G0', 'G1')}
            or reg['runtime_sha256'] != sha(RUNTIME)
            or canonical(reg['common']) != canonical(read(ORIGINAL)['common'])
            or reg['parent_registration_sha256'] != sha(ORIGINAL)
            or reg['previous_postmortem_sha256'] != sha(POSTMORTEM / 'verification.json')):
        raise ValueError('Frozen schedule/script/30-second budget differs')
    required = {path.relative_to(ROOT).as_posix() for path in implementation_sources()}
    if not required.issubset(reg['inputs']):
        raise ValueError('Actual implementation source missing from registration')
    verify_inputs(reg['inputs'])
    verify_inputs(reg['inputs'], root=OUT / 'source_snapshot')


def continue_batch(receipt, audit):
    facts = receipt.get('guard_facts', {})
    count = receipt.get('control_cycles')
    return bool(receipt.get('status') == 'finished' and receipt.get('valid') is True
        and receipt.get('stopped') is True and receipt.get('process_exit_confirmed') is True
        and receipt.get('returncode') == 0 and receipt.get('reset_attempted') == 1
        and type(count) is int and 0 < count <= MAX_CYCLES
        and receipt.get('physical_substeps') == 10 * count
        and receipt.get('count_precision', 'exact') == 'exact'
        and not receipt.get('nonfinite_fields') and facts.get('simulation_valid') is True
        and not facts.get('invalid_reasons') and not facts.get('motion_reasons')
        and audit.get('verified') is True and audit.get('script_verified') is True
        and audit.get('archive_sha256') == receipt.get('archive_sha256'))


def reconcile_receipt(folder, proof):
    """Retain exact completed counts; interruption has explicit lower/upper bounds."""
    folder = Path(folder)
    path = folder / 'receipt.json'
    malformed = False
    try:
        receipt = read(path) if path.exists() else {}
    except Exception as exc:
        receipt = dict(receipt_error=repr(exc)); malformed = True
    complete = receipt.get('status') == 'finished'
    receipt.setdefault('status', 'error')
    receipt.setdefault('reset_attempted', 0)
    receipt.setdefault('physical_substeps', 0)
    receipt.setdefault('control_cycles', 0)
    receipt.update(proof)
    if not complete or malformed:
        try:
            progress = read(folder / 'progress.json') if (folder / 'progress.json').exists() else {}
        except Exception as exc:
            progress = {}; receipt['progress_error'] = repr(exc)
        for target, key in [('physical_substeps', 'physical_substeps'),
                            ('control_cycles', 'cycles'), ('reset_attempted', 'reset_attempted')]:
            receipt[target] = max(receipt.get(target) or 0, progress.get(key) or 0)
        receipt.update(status='error', count_precision='lower_bound',
            physical_substeps_upper_bound=160000)
        if proof.get('started') and receipt['reset_attempted'] == 0:
            receipt['reset_attempted_unknown'] = True
    if proof.get('supervision_error') or proof.get('returncode') != 0:
        receipt['status'] = 'error'
    return receipt


def reconcile_batch(ledger, jobs, run_folder):
    episodes = []; failures = []
    for job in jobs:
        folder = Path(run_folder) / job['id']
        if not folder.exists():
            continue
        try:
            proof = read(folder / 'supervisor.json') if (folder / 'supervisor.json').exists() else dict(
                started=(folder / 'worker.claim').exists(), process_exit_confirmed=False, returncode=None)
            receipt = reconcile_receipt(folder, proof)
            audit = read(folder / 'audit.json') if (folder / 'audit.json').exists() else {}
        except Exception as exc:
            receipt = dict(case_id=job['id'], status='error', reconciliation_error=repr(exc),
                reset_attempted=0, reset_attempted_unknown=True, physical_substeps=0,
                control_cycles=0, count_precision='lower_bound', physical_substeps_upper_bound=160000)
            audit = {}
        receipt['case_id'] = job['id']
        receipt['audit_passed'] = continue_batch(receipt, audit)
        episodes.append(receipt)
        if not receipt['audit_passed']:
            failures.append(job['id'])
    initializations = sum(r.get('reset_attempted', 0) for r in episodes)
    unknown = sum(bool(r.get('reset_attempted_unknown')) for r in episodes)
    steps = sum(r.get('physical_substeps', 0) for r in episodes)
    upper = sum(r.get('physical_substeps_upper_bound', r.get('physical_substeps', 0)) for r in episodes)
    ledger.update(episodes=episodes, initialization_attempts=initializations, physical_substeps=steps,
        physical_substeps_upper_bound=upper, unknown_initialization_attempts_upper_bound=unknown,
        cumulative_initializations_lower_bound=415 + initializations,
        cumulative_initializations_upper_bound=415 + initializations + unknown,
        count_precision='lower_bound' if any(r.get('count_precision') == 'lower_bound' for r in episodes) else 'exact',
        unused_closed=4 - initializations - unknown)
    if not unknown:
        ledger['cumulative_initializations'] = 415 + initializations
    else:
        ledger.pop('cumulative_initializations', None)
    return failures


def execute_pairs(jobs, launch, audit_pair):
    if jobs != schedule():
        raise ValueError('Exactly four registered jobs required')
    for start in (0, 2):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(launch, jobs[start:start + 2]))
        audit_pair(results)


def verify_task_clock(*, stop_time, task_end_time, audit_end_time, settle_time):
    values = (stop_time, task_end_time, audit_end_time, settle_time)
    if (any(value is None or not math.isfinite(value) for value in values)
            or stop_time < 0 or stop_time > 30. + 1e-8
            or not stop_time - 1e-8 <= task_end_time <= stop_time + settle_time + 1e-8
            or audit_end_time > 32. + 1e-8):
        raise ValueError('Task deadline/settle/independent stop tail budget exceeded')


def verify_composition_log(log, expected, observation, controller_config):
    import numpy as np
    from tools.learning.five_axis_contract import field_slices
    if log['composition_inputs']['phase'] == 'SEARCH' and log['enabled']:
        radius = controller_config['spiral_radius_m']
        observed_reference = np.asarray(observation)[field_slices()['search_reference_xy_m']] * radius
        if (not log['reference_checked'] or abs(log['reference_radius_limit_m'] - radius) > 1e-15
                or not np.allclose(log['reference_xy_m'], observed_reference, rtol=0, atol=2e-11)):
            raise ValueError('Reference disk input differs from decision observation')
    for key in ('requested_residual', 'applied_residual', 'pre_stage_total', 'stage_clip_delta',
                'drive_clip_delta', 'unfiltered_stage_limited_total', 'stage_limited_total',
                'predicted_limited_command', 'zero_residual_limited_command', 'effective_command_delta'):
        if not np.allclose(log[key], expected[key], rtol=0, atol=1e-12):
            raise ValueError('Reconstructed profile composition differs: ' + key)
    if (log['reference_checked'] != expected['reference_checked']
            or abs(log['reference_filter_fraction'] - expected['reference_filter_fraction']) > 1e-12):
        raise ValueError('Reconstructed search disk filter differs')


def audit_archive(folder, reg, job):
    """Independent raw-byte, count, permission, action, clock and stop audit.

    Only legacy finite/observation/stop/reward mathematics are reused. Neither
    the old action mapping nor its 25-second registration/cycle cap is used.
    """
    import numpy as np
    from tools.learning.five_axis_contract import field_slices, permission
    from tools.learning.five_axis_preparation import _auditor, verify_rewards, verify_success_hold
    from tools.learning.global_residual_action import compose_command
    from tools.learning.observation import POLICY_PHASES
    folder = Path(folder); receipt = read(folder / 'receipt.json')
    if sha(folder / 'episode.json.gz') != receipt['archive_sha256']:
        raise ValueError('Raw archive byte digest differs')
    if sha(folder / 'model_used.xml') != receipt['model_xml_sha256']:
        raise ValueError('Used XML byte digest differs')
    raw = json.loads(gzip.decompress((folder / 'episode.json.gz').read_bytes()))
    contract = reg['profiles'][job['profile']]
    if (receipt.get('status') != 'finished' or not receipt.get('valid') or not receipt.get('stopped')
            or receipt.get('profile') != job['profile'] or receipt.get('contract') != contract
            or raw['version'] != contract['version'] or raw['observation_version'] != contract['observation_version']
            or raw['global_residual']['profile'] != job['profile']
            or raw['global_residual']['contract'] != contract
            or raw['case'] != job['case'] or receipt['case'] != job['case']):
        raise ValueError('Profile/30-second/case/interface binding differs')
    for key in COMMON:
        if canonical(receipt[key]) != canonical(reg['common'][key]):
            raise ValueError('Common physical/runtime domain changed: ' + key)
    facts = raw['evidence']['guard_facts']
    if (not facts['simulation_valid'] or facts['invalid_reasons'] or facts['motion_reasons']
            or raw['evidence']['interface_fault'] is not None or raw['evidence']['diagnostic_errors']):
        raise ValueError('Invalid, unqualified-motion or incomplete evidence')
    rows = raw['transitions']; trace = raw['trace']; count = len(rows)
    if (not 0 < count <= MAX_CYCLES or len(trace) != count + 1 or len(raw['cycle_peaks']) != count
            or receipt['control_cycles'] != count or receipt['physical_substeps'] != 10 * count
            or facts['checked_substeps'] != 10 * count or raw['cost']['physical_substeps'] != 10 * count
            or raw['cost']['initialization_attempts'] != 1 or raw['cost']['initializations_completed'] != 1
            or receipt['reset_attempted'] != 1):
        raise ValueError('Control-cycle/substep/initialization accounting differs')
    period = receipt['dynamic_config']['control_period']; dt = receipt['dynamic_config']['timestep']
    if abs(period - .002) > 1e-15 or abs(dt - .0002) > 1e-15:
        raise ValueError('Qualified native/control clock differs')
    cfg = receipt['controller_config']
    if cfg['total_action_time_s'] != 30. or cfg['search_time_s'] != 18.:
        raise ValueError('30-second total/18-second search contract differs')
    spans = field_slices(); schema = raw['observation_schema']
    if len(schema) != len(spans):
        raise ValueError('140-dimensional schema differs')
    for field, (name, span) in zip(schema, spans.items()):
        if (field['name'] != name or field['start'] != span.start or field['width'] != span.stop - span.start
                or len(field['scale']) != field['width'] or min(field['scale']) <= 0):
            raise ValueError('Observation schema/order differs')
        if name in ('total_budget_remaining_s', 'phase_elapsed_s') and field['scale'] != [30.]:
            raise ValueError('Time observation is not normalized to common 30 seconds')
    auditor = _auditor(); auditor._finite(raw)
    legacy = {key: span for key, span in spans.items() if span.stop <= 137}
    for cycle, state in enumerate(trace):
        if abs(state['time_s'] - cycle * period) > 1e-8:
            raise ValueError('Trace clock gap')
        for key, width in [('position_m', 3), ('quaternion_wxyz', 4), ('velocity_world', 6),
                           ('contact_wrench_M', 6), ('contact_wrench_G', 6), ('limited_command_world', 6)]:
            auditor._vector(state[key], width)
        if abs(np.linalg.norm(state['quaternion_wxyz']) - 1.) > 1e-6:
            raise ValueError('Quaternion normalization differs')
    script = DiagnosticScript(); nonzero = 0
    for cycle, row in enumerate(rows):
        obs = np.asarray(row['observation']); log = row['action_log']; inputs = log['composition_inputs']
        active = permission(obs)
        if active != row['action_active'] or permission(row['next_observation']) != row['next_action_active']:
            raise ValueError('Saved same-cycle permission differs')
        phase = POLICY_PHASES[int(obs[spans['policy_phase']].argmax())]
        expected_request = script.select(cycle, phase, active)
        if not np.array_equal(log['raw_action'], expected_request):
            raise ValueError('Saved request differs from preregistered script')
        nonzero += bool(any(expected_request))
        if abs(row['dt'] - period) > 1e-10 or log.get('profile') != job['profile']:
            raise ValueError('Action clock/profile differs')
        auditor._observation(row['observation'][:137], trace, cycle, legacy)
        auditor._observation(row['next_observation'][:137], trace, cycle + 1, legacy)
        for observed, index in [(row['observation'], cycle), (row['next_observation'], cycle + 1)]:
            remaining = max(0., 30. - trace[index]['time_s']) / 30.
            if abs(observed[spans['total_budget_remaining_s'].start] - remaining) > 1e-6:
                raise ValueError('Remaining-time observation differs from 30-second clock')
        scale = np.array([.001] * 3 + [.03] * 3)
        reference_failure = log.get('reference_failure') == 'RESIDUAL_REFERENCE_INFEASIBLE'
        if not reference_failure and (inputs['phase'] != phase or log['enabled'] != active
                or not np.allclose(inputs['base_command'], obs[spans['base_command']] * scale, rtol=0, atol=2e-9)):
            raise ValueError('Command phase/base/permission binding differs')
        if reference_failure and (inputs['phase'] != 'FAILED' or log['enabled'] or any(inputs['base_command'])):
            raise ValueError('Malformed reference-infeasible failure')
        if (not np.allclose(inputs['previous_limited_command'], obs[spans['previous_limited_command']] * scale, rtol=0, atol=2e-9)
                or abs(inputs['dt'] - period) > 1e-10):
            raise ValueError('Previous command/clock binding differs')
        _, expected = compose_command(inputs['base_command'], expected_request, profile=job['profile'],
            phase=inputs['phase'], enabled=log['enabled'], previous_limited=inputs['previous_limited_command'],
            dt=inputs['dt'], reference_xy=log.get('reference_xy_m'), radius=log.get('reference_radius_limit_m', .0004))
        verify_composition_log(log, expected, obs, cfg)
        if (row['action'] != expected['experience_action']
                or log['actual_end_limited_command'] != trace[cycle + 1]['limited_command_world']
                or not active and any(row['action'])):
            raise ValueError('Saved action/physical command endpoint differs')
        physical = int(obs[spans['physical_phase']].argmax())
        next_physical = int(np.asarray(row['next_observation'])[spans['physical_phase']].argmax())
        if physical != 2 and physical == next_physical and not np.allclose(
                log['actual_end_limited_command'], expected['predicted_limited_command'], rtol=0, atol=1e-12):
            raise ValueError('Ordinary actual drive differs from reconstructed limit')
    verify_rewards(raw, final_reason=receipt['final_reason'])
    stop = auditor._stop_math(dict(trace=trace, events=raw['evidence']['environment_events'],
        stop_samples=raw['evidence']['stop_samples']), dict(receipt,
            audit_end_time_s=trace[-1]['time_s'], stop_time_s=raw['evidence']['stop_time_s']), dt, period)
    task_end = raw['evidence']['task_end_time_s']
    verify_task_clock(stop_time=raw['evidence']['stop_time_s'], task_end_time=task_end,
        audit_end_time=trace[-1]['time_s'], settle_time=cfg['settle_time_s'])
    classified = 'CONTACT_GUARD' if facts['contact_reasons'] else (
        'FULL_SUCCESS' if receipt['final_reason'] == 'GEOMETRIC_SUCCESS' else 'TASK_FAILURE')
    if classified != raw['outcome']['task_outcome']:
        raise ValueError('Task result differs from physical facts')
    if classified == 'FULL_SUCCESS':
        verify_success_hold(trace, task_end_time_s=task_end, period=period, criteria=receipt['finish_criteria'])
    proof = dict(verified=True, script_verified=True, archive_sha256=receipt['archive_sha256'],
        registration_sha256=sha(OUT / 'registration.json'), rows=count, stop=stop,
        script=script.state(), nonzero_request_cycles=nonzero, coverage='executed' if nonzero else 'not_covered',
        training_admitted=False, replay_publications=0)
    return raw, receipt, proof


def worker(job_id):
    reg = read(OUT / 'registration.json'); validate(reg)
    job = next(job for job in reg['schedule'] if job['id'] == job_id)
    folder = OUT / 'run' / job_id
    with (folder / 'worker.claim').open('x') as claim:
        claim.write(str(os.getpid()))
    blocker = NoLearning(); sys.meta_path.insert(0, blocker)
    receipt = dict(case_id=job_id, profile=job['profile'], contract=reg['profiles'][job['profile']],
        status='initializing', reset_attempted=0, reset_completed=0, physical_substeps=0, control_cycles=0,
        valid=False, stopped=False, policy_calls=0, neural_policy_calls=0, training_updates=0,
        replay_publications=0, final_test_episodes=0, registration_sha256=sha(OUT / 'registration.json'))
    env = session = None; raw = {}; started = time.monotonic(); script = DiagnosticScript()
    write(folder / 'receipt.json', receipt)
    try:
        from tools.learning.runtime import select_runtime, verify_runtime, active_package
        select_runtime(RUNTIME, expected_digest=reg['runtime_sha256'])
        runtime = verify_runtime(active_package())
        from tools.learning.global_residual_session import session_class
        from tools.learning.five_axis_collection import collect_episode, CollectionError
        from tools.learning.newton_profile import build_model_xml
        from tools.validation.yaw_pilot import environment_class, YawContactCase
        env = environment_class()()
        model_bytes = model_archive_bytes(build_model_xml(env.profile))
        (folder / 'model_used.xml').write_bytes(model_bytes)
        receipt.update(actual_common(env, runtime, model_bytes))
        if any(canonical(receipt[key]) != canonical(reg['common'][key]) for key in COMMON):
            raise ValueError('Current environment differs from common qualified domain')
        Base = session_class(job['profile'])
        class BoundedSession(Base):
            def advance_cycle(self, action):
                if time.monotonic() - started > reg['max_worker_wall_s'] or (OUT / 'STOP').exists():
                    raise RuntimeError('Wall/external bound; no retry')
                before = self.prepare_cycle()
                # Collector skips policy() while permission is absent: observe
                # every cycle here so an interruption can never resume later.
                expected = script.select(self.cycle_id, before.controller_state['phase'], before.residual_enabled)
                if list(action) != expected:
                    raise ValueError('Collector input differs from scripted same-cycle request')
                result = super().advance_cycle(action)
                result.action_log['diagnostic_script'] = script.state()
                if self.cycle_id % 100 == 0:
                    write(folder / 'progress.json', dict(cycles=self.cycle_id, simulation_s=self.cycle_id * .002,
                        physical_substeps=env.physical_steps, reset_attempted=1, neural_policy_calls=0,
                        training_updates=0, phase=result.next_snapshot.controller_state['phase'], script=script.state()))
                return result
        session = BoundedSession(env); point = YawContactCase(**job['case'])
        def policy(observation):
            before = session.prepare_cycle()
            return script.select(session.cycle_id, before.controller_state['phase'], before.residual_enabled)
        receipt.update(case=asdict(point), reset_attempted=1)
        write(folder / 'receipt.json', receipt)
        try:
            raw = collect_episode(session, point, policy=policy, seed=reg['seed'], max_cycles=MAX_CYCLES)
        except CollectionError as exc:
            raw = exc.archive
            raise
        receipt.update(status='finished', reset_completed=1, valid=raw['outcome']['simulation_valid'],
            stopped=raw['outcome']['physical_stopped'], outcome=raw['outcome']['task_outcome'],
            final_reason=session.reason, finish_criteria=session.finish_criteria,
            controller_config=asdict(session.controller.config), controller_metadata=session.controller.metadata(),
            initialization_guard_config=asdict(env.guard_config),
            task_time_s=session.task_end_time, stop_time_s=session.stop_time,
            audit_end_time_s=float(env.data.time))
    except BaseException as exc:
        receipt.update(status='error', error=repr(exc))
        raise
    finally:
        if session is not None:
            raw['version'] = session.contract['version']
            raw['global_residual'] = dict(profile=job['profile'], contract=session.contract,
                script_contract=script_contract(), script_final=script.state(), training_admitted=False)
            receipt['control_cycles'] = getattr(session, 'cycle_id', 0)
        if env is not None:
            receipt.update(physical_substeps=env.physical_steps, guard_facts=env.guard_facts)
        receipt.update(elapsed_wall_s=time.monotonic() - started, script=script.state())
        publish_archive(folder, raw, receipt)
    # Keep NoLearning installed through raw audit; it needs no tensor library.
    raw, receipt, proof = audit_archive(folder, reg, job)
    write(folder / 'audit.json', proof)
    if blocker in sys.meta_path:
        sys.meta_path.remove(blocker)
    print(json.dumps(dict(job=job_id, verified=True, final_reason=receipt['final_reason'],
        coverage=proof['coverage'], script=proof['script'])), flush=True)


def run():
    reg = read(OUT / 'registration.json'); validate(reg)
    (OUT / 'run').mkdir()  # A failed/partial launch also consumes this claim.
    ledger = dict(status='RUNNING', episodes=[], initialization_attempts=0, physical_substeps=0,
        cumulative_before=415, neural_policy_calls=0, training_updates=0, replay_publications=0,
        final_test_episodes=0, registration_sha256=sha(OUT / 'registration.json'))
    write(OUT / 'ledger.json', ledger); started = time.monotonic()
    def launch(job):
        validate(reg)
        folder = OUT / 'run' / job['id']; folder.mkdir()
        return supervise([str(PYTHON), '-B', '-X', 'utf8', str(Path(__file__).resolve()), '--worker', job['id']],
            folder, timeout=reg['max_worker_wall_s'] + 180)
    def audit_pair(results):
        validate(reg)
        failures = reconcile_batch(ledger, reg['schedule'], OUT / 'run')
        write(OUT / 'ledger.json', ledger)
        if failures:
            raise RuntimeError('Invalid/save/audit/count/source/exit failure; batch stops: ' + ', '.join(failures))
        # Same task/controller settings apart from the registered action profile.
        pair = ledger['episodes'][-2:]
        for key in ('controller_config', 'finish_criteria', 'initialization_guard_config'):
            if canonical(pair[0].get(key)) != canonical(pair[1].get(key)):
                raise ValueError('Paired common control setting differs: ' + key)
    try:
        execute_pairs(reg['schedule'], launch, audit_pair)
        ledger['status'] = 'COMPLETED'
    except BaseException as exc:
        ledger.update(status='STOPPED', error=repr(exc))
        raise
    finally:
        if ledger['status'] == 'RUNNING':
            ledger['status'] = 'STOPPED'
        reconcile_batch(ledger, reg['schedule'], OUT / 'run')
        ledger['elapsed_wall_s'] = time.monotonic() - started
        write(OUT / 'ledger.json', ledger)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare', action='store_true')
    group.add_argument('--run', action='store_true')
    group.add_argument('--launch', action='store_true')
    group.add_argument('--worker')
    args = parser.parse_args()
    if args.prepare:
        prepare()
    elif args.worker:
        worker(args.worker)
    elif args.run:
        run()
    else:
        with (OUT / 'launcher.claim').open('x'):
            pass
        proof = dict(started=False, process_exit_confirmed=False, returncode=None)
        try:
            with (OUT / 'launcher.log').open('xb') as log:
                proc = subprocess.Popen([str(PYTHON), '-B', '-X', 'utf8', str(Path(__file__).resolve()), '--run'],
                    cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                proof.update(started=True, pid=proc.pid, supervisor_pid=os.getpid())
                write(OUT / 'process_started.json', proof)
                try:
                    proof['returncode'] = proc.wait()
                except BaseException as exc:
                    proof['supervision_error'] = repr(exc)
                    # Supervisor must finish its children before this launcher exits.
                    proof['returncode'] = proc.wait()
                    raise
                finally:
                    proof['process_exit_confirmed'] = proc.poll() is not None
        finally:
            write(OUT / 'process_exit.json', proof)
        return proof['returncode']
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
