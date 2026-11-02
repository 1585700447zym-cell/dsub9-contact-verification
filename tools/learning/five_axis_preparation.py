"""Frozen five-axis preparation, raw evidence audit and launch admission."""
from copy import deepcopy
from dataclasses import asdict
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import numpy as np
from .five_axis_contract import VERSION, field_slices, learning_config

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'deliverables/learning_chain/five_axis_pretraining_20261023'
PARENT = ROOT / 'deliverables/learning_chain/b2_yaw_pilot_v2_20261023/run/YAW_P10/receipt.json'
RUNTIME = ROOT / 'deliverables/learning_chain/b2_repaired_cycle_v2_20260928/runtime.json'
AUDITOR = ROOT / 'deliverables/learning_chain/b2_newton_sac_preparation_20261016/newton_raw_audit.py'
COMMON = ('dynamic_config', 'effective_kd', 'model_xml_sha256', 'actual_model', 'runtime')
KINDS = ('ZERO_P10', 'PULSE_P10', 'PULSE_M10')


def read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def canonical(value): return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def verify_inputs(pins, root=ROOT):
    for name, digest in pins.items():
        target = (root / name).resolve()
        if not target.is_relative_to(root.resolve()) or sha(target) != digest:
            raise ValueError('Frozen input changed: ' + name)


def freeze_sources(paths, *, snapshot_only=(), folder, root=ROOT):
    pins = {}
    for path in list(paths) + list(snapshot_only):
        path = Path(path); name = path.relative_to(root).as_posix()
        target = Path(folder) / name; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
        if path in paths: pins[name] = sha(path)
    return pins


def preparation_scope():
    return dict(version='five_axis_pretraining_v1', max_initializations=3, retries=0,
                cumulative_before=372, case_ids=list(KINDS), formal_training_updates=0,
                max_cycles=14500, max_worker_wall_s=1800, seed=2026092716)


def cases():
    return [dict(name=name, x_offset_m=.0003, y_offset_m=.0003, roll_rad=math.radians(-1),
                 pitch_rad=math.radians(1), yaw_rad=math.radians(angle),
                 start_origin_z_m=-.005, target_depth_m=.005)
            for name, angle in [('YAW_P10', 1), ('YAW_M10', -1), ('YAW_P15', 1.5), ('YAW_M15', -1.5)]]


def training_plan():
    schedule = []
    for stage in ('warmup', 'online', 'development'):
        for point in cases():
            schedule.append(dict(id=stage + '_' + point['name'], stage=stage, case=point,
                updates_after=500 if stage == 'online' else 0, data_use='development_only',
                publish=stage != 'development'))
    return dict(version='five_axis_development_training_v1', config=learning_config(), schedule=schedule,
        max_initializations=12, max_cycles=14500, max_worker_wall_s=1800, max_wall_s=21600,
        max_physical_substeps=12 * 14500 * 10, formal_updates=2000, final_test_episodes=0,
        retries=0, warmup_episodes=4, updates_per_online_episode=500,
        update_sampling='one uniform batch of 256 per update at complete episode boundaries',
        development_goal=dict(full_successes_at_least=2, evaluated_points=4, baseline_full_successes=0),
        stop_on=['invalid_simulation', 'unqualified_stop_or_archive', 'motion_violation', 'update_failure'],
        auto_upgrade=False, baseline_cases=[p['name'] for p in cases()])


def qualification_action(kind, cycle):
    if kind not in KINDS or type(cycle) is not int or cycle < 0:
        raise ValueError('Registered qualification kind and cycle required')
    action = np.zeros(5)
    if kind != 'ZERO_P10' and cycle < 300:
        segment, part = divmod(cycle, 30)
        if part < 20: action[segment // 2] = 1. if segment % 2 == 0 else -1.
    return action


def compare_zero_trace(actual, baseline):
    if len(actual) != len(baseline): raise ValueError('Zero residual trajectory length differs')
    keys = ('time_s', 'position_m', 'quaternion_wxyz', 'velocity_world', 'contact_wrench_M',
            'contact_wrench_G', 'limited_command_world')
    maxima = {key: 0. for key in keys}
    for a, b in zip(actual, baseline):
        if a['phase'] != b['phase']: raise ValueError('Zero residual physical stage differs')
        for key in keys:
            left, right = np.asarray(a[key]), np.asarray(b[key])
            if left.shape != right.shape or not np.isfinite(left).all():
                raise ValueError('Malformed zero trajectory')
            delta = float(np.max(np.abs(left - right)))
            maxima[key] = max(maxima[key], delta)
            if delta > 1e-12: raise ValueError('Zero residual physical trajectory differs: ' + key)
    return dict(rows=len(actual), max_absolute_difference=maxima)


def validate_transitions(rows):
    from .five_axis_replay import FiveAxisReplay
    prepared = FiveAxisReplay(capacity=14500)._prepare(rows)
    return dict(rows=len(rows), active_rows=int(prepared['action_active'].sum()))


def validate_resume_boundary(destination, ledger, latest, registration_pin, admission_pin):
    index = latest['next_schedule_index']; schedule = training_plan()['schedule']
    if (type(index) is not int or not 0 <= index <= len(schedule)
            or latest['registration_sha256'] != registration_pin or latest['admission_sha256'] != admission_pin
            or len(ledger['episodes']) != index
            or (index < len(schedule) and (Path(destination) / schedule[index]['id']).exists())):
        raise ValueError('Only an untouched next episode at a matching complete boundary can resume')
    return index


def verify_rewards(raw, *, final_reason):
    maximum = 0.; target = raw['case']['target_depth_m']; rows = raw['transitions']
    terminal_values = dict(FULL_SUCCESS=10., CONTACT_GUARD=-10., MOTION_VIOLATION=-10., TASK_FAILURE=-2.)
    terminal = 0. if final_reason == 'EXTERNAL_TRUNCATION' else terminal_values[raw['outcome']['task_outcome']]
    for i, (row, peaks) in enumerate(zip(rows, raw['cycle_peaks'])):
        dt = row['dt']; advance = raw['trace'][i + 1]['position_m'][2] - raw['trace'][0]['position_m'][2]
        new_max = max(maximum, min(target, max(0., advance)))
        terms = dict(progress=5 * (new_max - maximum) / target, time=-.1 * dt,
            force=-.2 * dt * (peaks['force_N'] / 5.) ** 2,
            torque=-.2 * dt * (peaks['torque_G_Nm'] / .1) ** 2,
            terminal=terminal if i == len(rows) - 1 else 0.)
        terms['total'] = sum(terms.values()); maximum = new_max
        if (set(terms) != set(row['reward_terms'])
                or any(abs(row['reward_terms'][key] - value) > 1e-9 for key, value in terms.items())
                or abs(row['reward'] - terms['total']) > 1e-9):
            raise ValueError('N2 reward accounting differs')


def verify_success_hold(trace, *, task_end_time_s, period, criteria):
    from tools.model.layered_task import functional_finish
    end = round(task_end_time_s / period); hold = math.ceil(criteria['hold_s'] / period)
    stable = trace[max(0, end - hold):end + 1]
    if len(stable) < hold + 1 or not all(functional_finish(row, criteria) for row in stable):
        raise ValueError('Current nine-pin success/hold differs from task-window evidence')


def verify_action_mapping(row):
    from .five_axis_action import compose_command, map_residual
    from .observation import POLICY_PHASES
    spans = field_slices(); obs = np.asarray(row['observation']); log = row['action_log']
    inputs = log['composition_inputs']; base = np.asarray(inputs['base_command'])
    previous = np.asarray(inputs['previous_limited_command']); scale = [.001] * 3 + [.03] * 3
    reference_failure = log.get('reference_failure') == 'RESIDUAL_REFERENCE_INFEASIBLE'
    if reference_failure:
        if inputs['phase'] != 'FAILED' or log['enabled'] or np.any(base): raise ValueError('Invalid failure command')
    elif (inputs['phase'] != POLICY_PHASES[int(obs[spans['policy_phase']].argmax())]
            or log['enabled'] != row['action_active']
            or not np.allclose(base, obs[spans['base_command']] * scale, rtol=0, atol=2e-9)):
        raise ValueError('Composition base/phase/permission differs from decision snapshot')
    if (not np.allclose(previous, obs[spans['previous_limited_command']] * scale, rtol=0, atol=2e-9)
            or abs(inputs['dt'] - row['dt']) > 1e-10):
        raise ValueError('Composition previous command/clock differs from decision snapshot')
    _, expected = compose_command(base, log['raw_action'], phase=inputs['phase'], enabled=log['enabled'],
        previous_limited=previous, dt=inputs['dt'], reference_xy=log.get('reference_xy_m'),
        radius=log.get('reference_radius_limit_m', .0004))
    if log.get('reference_checked'):
        if not np.allclose(log['reference_xy_m'], obs[spans['search_reference_xy_m']] * .0004, rtol=0, atol=2e-11):
            raise ValueError('Reference envelope differs from snapshot')
    for key in ('requested_residual', 'applied_residual', 'stage_limited_total',
                'predicted_limited_command', 'zero_residual_limited_command', 'effective_command_delta'):
        if not np.allclose(log[key], expected[key], rtol=0, atol=1e-12):
            raise ValueError('Five-axis mapping/composition differs: ' + key)
    if (log['experience_action'] != expected['experience_action']
            or row['action'] != log['experience_action']):
        raise ValueError('Executed action/drive command differs')
    physical = int(obs[spans['physical_phase']].argmax())
    next_physical = int(np.asarray(row.get('next_observation', obs))[spans['physical_phase']].argmax())
    # RETRACT owns Z internally; native stop/recovery can reset the command.
    # The caller independently binds actual_end to the physical endpoint trace.
    # Ordinary unchanged-phase drive and all free pulse segments must still
    # equal the reconstructed limited command, including their exact gain.
    if physical != 2 and physical == next_physical:
        if not np.allclose(log['actual_end_limited_command'], expected['predicted_limited_command'], rtol=0, atol=1e-12):
            raise ValueError('Ordinary drive command differs from composition')


def verify_pulse_schedule(raw, receipt):
    if (len(raw['transitions']) != 1300 or receipt['final_reason'] != 'EXTERNAL_TRUNCATION'
            or abs(raw['evidence']['stop_time_s'] - .6) > 1e-8
            or abs(raw['evidence']['task_end_time_s'] - .6) > 1e-8):
        raise ValueError('Pulse cutoff/complete stop tail differs')
    for cycle, row in enumerate(raw['transitions']):
        expected = qualification_action(receipt['case_id'], cycle).tolist()
        if row['action'] != expected or row['action_active'] != (cycle < 300):
            raise ValueError('Prescribed pulse/zero/tail action differs')
        verify_action_mapping(row)


def _auditor():
    spec = importlib.util.spec_from_file_location('_five_axis_stop_math', AUDITOR)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def audit_episode(raw, receipt, registration, *, qualification=False):
    if (receipt.get('status') != 'finished' or receipt.get('valid') is not True
            or receipt.get('stopped') is not True):
        raise ValueError('Completed valid episode and stop required')
    for key in COMMON:
        if canonical(receipt[key]) != canonical(registration['common'][key]):
            raise ValueError('Physical/runtime domain changed: ' + key)
    facts = raw['evidence']['guard_facts']
    if (not facts['simulation_valid'] or facts['invalid_reasons'] or facts['motion_reasons']
            or raw['evidence']['interface_fault'] is not None
            or raw['evidence']['diagnostic_errors']):
        raise ValueError('Invalid or out-of-qualified-motion-domain record')
    count = len(raw['transitions']); trace = raw['trace']; dt = receipt['dynamic_config']['timestep']
    period = receipt['dynamic_config']['control_period']
    if (not 0 < count <= 14500 or len(trace) != count + 1 or len(raw['cycle_peaks']) != count
            or receipt['physical_substeps'] != count * 10 or facts['checked_substeps'] != count * 10
            or raw['cost']['physical_substeps'] != count * 10
            or raw['cost']['initializations_completed'] != 1
            or raw['cost']['initialization_attempts'] != 1):
        raise ValueError('Incomplete cycle/substep/cost evidence')
    if raw['version'] != VERSION or raw['observation_version'] != 'five_axis_short_history_N2_v1':
        raise ValueError('Wrong learning interface version')
    schema = raw['observation_schema']; spans = field_slices()
    if len(schema) != len(spans): raise ValueError('Schema width/order differs')
    for field, (name, span) in zip(schema, spans.items()):
        if (field['name'] != name or field['start'] != span.start or field['width'] != span.stop - span.start
                or len(field['scale']) != field['width'] or min(field['scale']) <= 0):
            raise ValueError('Schema differs')
    if schema[0]['scale'] != ([5.] * 3 + [.1] * 3) * 4: raise ValueError('Wrong N2 force scale')
    auditor = _auditor(); auditor._finite(raw)
    legacy_spans = {key: value for key, value in spans.items() if value.stop <= 137}
    for i, row in enumerate(trace):
        if abs(row['time_s'] - i * period) > 1e-8: raise ValueError('Control clock gap')
        for key, width in [('position_m', 3), ('quaternion_wxyz', 4), ('velocity_world', 6),
                           ('contact_wrench_M', 6), ('contact_wrench_G', 6), ('limited_command_world', 6)]:
            auditor._vector(row[key], width)
        if abs(np.linalg.norm(row['quaternion_wxyz']) - 1.) > 1e-6: raise ValueError('Invalid quaternion')
    point = receipt['case']
    if canonical(raw['case']) != canonical(point) or canonical(point) not in [canonical(p) for p in cases()]:
        raise ValueError('Case binding/scope differs')
    from tools.validation.run_contact_cases import _quaternion
    from types import SimpleNamespace
    if (not np.allclose(trace[0]['position_m'], [point['x_offset_m'], point['y_offset_m'], point['start_origin_z_m']], atol=1e-12, rtol=0)
            or not np.allclose(trace[0]['quaternion_wxyz'], _quaternion(SimpleNamespace(**point)), atol=1e-12, rtol=0)):
        raise ValueError('Initial pose/order differs')
    for i, row in enumerate(raw['transitions']):
        if abs(row['dt'] - period) > 1e-10: raise ValueError('Policy period changed')
        auditor._observation(row['observation'][:137], trace, i, legacy_spans)
        auditor._observation(row['next_observation'][:137], trace, i + 1, legacy_spans)
        if row['action_log']['experience_action'] != row['action']: raise ValueError('Experience action differs')
        verify_action_mapping(row)
        if row['action_log']['actual_end_limited_command'] != trace[i + 1]['limited_command_world']:
            raise ValueError('Action execution differs from physical trace')
        if not row['action_active'] and any(row['action']): raise ValueError('Inactive action')
        if any(abs(x) > .020000000001 for x in row['action_log']['stage_limited_total'][3:]):
            raise ValueError('Angular stage cap exceeded')
    result = validate_transitions(raw['transitions'])
    verify_rewards(raw, final_reason=receipt['final_reason'])
    stop_receipt = dict(receipt, audit_end_time_s=trace[-1]['time_s'],
                        stop_time_s=raw['evidence']['stop_time_s'])
    result['stop'] = auditor._stop_math(dict(trace=trace, events=raw['evidence']['environment_events'],
        stop_samples=raw['evidence']['stop_samples']), stop_receipt, dt, period)
    if not raw['outcome']['physical_stopped']: raise ValueError('Outcome stop differs')
    classified = ('CONTACT_GUARD' if facts['contact_reasons'] else
                  'FULL_SUCCESS' if receipt['final_reason'] == 'GEOMETRIC_SUCCESS' else 'TASK_FAILURE')
    if classified != raw['outcome']['task_outcome']: raise ValueError('Outcome differs from physical facts')
    if classified == 'FULL_SUCCESS':
        verify_success_hold(trace, task_end_time_s=raw['evidence']['task_end_time_s'],
                            period=period, criteria=receipt['finish_criteria'])
    result.update(verified=True, task_outcome=raw['outcome']['task_outcome'])
    if qualification and receipt['case_id'] == 'ZERO_P10':
        old = json.loads(gzip.decompress((PARENT.parent / 'episode.json.gz').read_bytes()))
        result['zero_trajectory'] = compare_zero_trace(trace, old['trace'])
        reasons = [event['reason'] for event in raw['evidence']['environment_events']]
        if (not all(reason in reasons for reason in ('RECOVERY_ACCEPTED', 'B2_RECOVERY_RESUMED'))
                or not any(row.get('policy_phase') == 'UNLOAD' for row in trace)):
            raise ValueError('Natural unload/recovery not covered')
    if qualification and receipt['case_id'].startswith('PULSE'):
        verify_pulse_schedule(raw, receipt)
        signs = []
        for segment in range(10):
            axis = segment // 2; sign = 1. if segment % 2 == 0 else -1.
            command_axis = [0, 1, 3, 4, 5][axis]
            selected = raw['transitions'][segment * 30 + 15:segment * 30 + 20]
            motion = trace[segment * 30 + 16:segment * 30 + 21]
            if len(selected) != 5: raise ValueError('Pulse segment missing')
            for offset, row in enumerate(selected, segment * 30 + 15):
                expected = qualification_action(receipt['case_id'], offset).tolist()
                if row['action'] != expected or not row['action_active']: raise ValueError('Pulse masked or changed')
            actual = float(np.mean([r['velocity_world'][command_axis] for r in motion]))
            if actual * sign <= 0: raise ValueError('Actual motion direction differs')
            signs.append(dict(axis=axis, sign=sign, mean_actual_velocity=actual))
        if max(np.linalg.norm(r['contact_wrench_M']) for r in trace[:301]) > 1e-9:
            raise ValueError('Pulse directional qualification was not in free motion')
        result['pulse_signs'] = signs
    return result


def audit_archive(folder, registration, *, qualification=False):
    folder = Path(folder); receipt = read(folder / 'receipt.json')
    if sha(folder / 'episode.json.gz') != receipt['archive_sha256']: raise ValueError('Archive byte pin differs')
    if sha(folder / 'model_used.xml') != receipt['model_xml_sha256']: raise ValueError('Actual XML bytes differ')
    raw = json.loads(gzip.decompress((folder / 'episode.json.gz').read_bytes()))
    proof = audit_episode(raw, receipt, registration, qualification=qualification)
    return raw, receipt, proof


def check_ready(out=OUT):
    out = Path(out); admission = read(out / 'admission.json'); registration = read(out / 'registration.json')
    if (admission['ready'] is not True or admission['registration_sha256'] != sha(out / 'registration.json')
            or canonical(registration['training_plan']) != canonical(training_plan())):
        raise ValueError('Readiness registration/config differs')
    verify_inputs(registration['inputs'])
    if set(admission['artifacts']) != set(KINDS): raise ValueError('Incomplete qualifications')
    for kind in KINDS:
        folder = out / 'run' / kind
        expected = admission['artifacts'][kind]
        if any(sha(folder / name) != pin for name, pin in expected.items()):
            raise ValueError('Qualification evidence changed')
        _, _, proof = audit_archive(folder, registration, qualification=True)
        if not proof['verified']: raise ValueError('Qualification failed')
    if sha(out / 'initial_checkpoint/manifest.json') != admission['checkpoint_digest']:
        raise ValueError('Initial checkpoint changed')
    from .five_axis_checkpoint import load_checkpoint
    trainer = load_checkpoint(out / 'initial_checkpoint', expected_digest=admission['checkpoint_digest'],
                              config=registration['training_plan']['config'])
    if trainer.update_attempts or len(trainer.replay): raise ValueError('Initial trainer must be untrained')
    return admission, registration
