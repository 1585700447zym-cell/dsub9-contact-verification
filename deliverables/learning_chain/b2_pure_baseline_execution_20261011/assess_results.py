"""Read completed archives, compare registered development points, and retain all failures."""
import csv
import gzip
import importlib.abc
import importlib.util
import json
import math
from pathlib import Path
import shutil
import sys
from datetime import datetime

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
PREP = ROOT / 'deliverables/learning_chain/b2_pure_baseline_preparation_20261011'
S21 = ROOT / 'deliverables/learning_chain/b2_joint_efficiency_diagnosis_20261010'


class NoScience(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in ('numpy', 'mujoco', 'torch', 'stable_baselines3'):
            raise AssertionError('Result analysis must not execute scientific runtime')


sys.meta_path.insert(0, NoScience())
sys.path.insert(0, str(PREP))
import contract as c
spec = importlib.util.spec_from_file_location('frozen_phase_analysis', S21 / 'analyze.py')
analysis = importlib.util.module_from_spec(spec); spec.loader.exec_module(analysis)
spec = importlib.util.spec_from_file_location('zero_action_check', PREP / 'baseline_rollout.py')
zero = importlib.util.module_from_spec(spec); spec.loader.exec_module(zero)


def tail_pass(rows, end, dt=.0002):
    """Independently recalculate the frozen 0.1s stop window from saved samples."""
    tail = [r for r in rows if r['time_s'] >= end - .1 - dt / 2]
    return bool(tail and tail[0]['time_s'] <= end - .1 + dt / 2 and
        abs(tail[-1]['time_s'] - end) <= dt / 2 and
        all(0 < b['time_s'] - a['time_s'] <= dt * 1.01 for a, b in zip(tail, tail[1:])) and
        all(math.isfinite(r['linear_m_s']) and math.isfinite(r['angular_rad_s']) and
            r['linear_m_s'] <= 1e-5 and r['angular_rad_s'] <= .001 for r in tail))


def stop_pass(raw):
    phase = None; started = None
    for event in raw['events']:
        current = event.get('phase')
        if current is None: continue
        if current == 'STOPPING':
            if phase != 'STOPPING': started = float(event['time_s'])
        else: started = None
        phase = current
    end = raw['audit_end_time_s']; dt = .0002
    return bool(started is not None and end >= started + 2. - 1e-9 and
        tail_pass([r for r in raw['stop_samples'] if r['time_s'] <= started + 2. + dt / 2], started + 2.) and
        tail_pass(raw['stop_samples'], end))


def record(raw, role, path, config):
    point = next(p for p in config['cases'] if p['id'] == raw['case_id'])
    assert raw['comparison_key'] == config['common_key'] and raw['case'] == point
    c.check_pose(point, raw['trace'][0])
    times = analysis.validate_alignment(raw)
    labels = [analysis.phase_of(t['observation'], raw['observation_schema']) for t in raw['transitions']]
    phases = analysis.time_parts(times, labels, raw['task_end_time_s'])
    assert abs(math.fsum(phases.values()) - raw['task_end_time_s']) < 1e-9
    assert raw['physical_substeps'] == 10 * raw['control_cycles']
    stopped = stop_pass(raw); outcome = raw['outcome']; assert stopped == outcome['physical_stopped']
    if role == 'pure_B2':
        assert raw['role'] == role and raw['policy_calls'] == 0 and raw['optimizer_steps'] == 0
        assert raw['policy_sha256'] is None
        for action in raw['actions']: zero.check_zero_log(action)
    final = analysis.precise(raw['trace'][-1])
    task_index = min(range(len(times)), key=lambda i: abs(times[i] - raw['task_end_time_s']))
    assert abs(times[task_index] - raw['task_end_time_s']) < 1e-9
    valid = outcome['simulation_valid'] is True
    success = bool(outcome['task_outcome'] == 'FULL_SUCCESS' and valid and stopped and
                   not any(outcome['guard_violations'].values()))
    if outcome['task_outcome'] == 'FULL_SUCCESS': assert success
    task_transitions = raw['transitions'][:task_index]; task_actions = raw['actions'][:task_index]
    active = [(a, t) for a, t in zip(task_actions, task_transitions) if t['action_active']]
    active_s = math.fsum(t['dt'] for a, t in active)
    axes = (0, 1, 3, 4)
    residual_audit = {key: [math.fsum(abs(a[key][j]) * t['dt'] for a, t in active) for j in axes]
                      for key in ('requested_residual', 'applied_residual', 'effective_command_delta')}
    residual_audit.update(active_time_s=active_s,
        max_predicted_executed_command_error=max((abs(a['predicted_limited_command'][j] - a['actual_end_limited_command'][j])
                                                 for a, t in active for j in range(6)), default=0.),
        physical_XY_path_um=math.fsum(math.dist(a['position_m'][:2], b['position_m'][:2])
                                     for a, b in zip(raw['trace'][:task_index], raw['trace'][1:task_index+1])) * 1e6)
    maximum = 0.; no_progress_s = 0.
    for label, transition in zip(labels[:task_index], task_transitions):
        current = max(maximum, min(point['target_depth_m'], max(0., transition['advance_m'])))
        if label in ('INSERT', 'SEARCH') and current <= maximum + 1e-12: no_progress_s += transition['dt']
        maximum = current
    return dict(role=role, case_id=point['id'], archive_path=str(path), sha256=c.sha(path),
        task_outcome=outcome['task_outcome'], simulation_valid=valid, physical_stopped=stopped,
        guard=any(outcome['guard_violations'].values()), functional_success=success,
        task_time_s=raw['task_end_time_s'], penalized_time_s=raw['task_end_time_s'] if success else 26. if valid and stopped else None,
        force_mN=raw['peaks']['force_N'] * 1000, torque_G_mNm=raw['peaks']['torque_G_Nm'] * 1000,
        penetration_um=raw['peaks']['penetration_m'] * 1e6, final_xy_um=final['xy_um'],
        final_angle_deg=final['angle_to_identity_deg'], final_roll_deg=final['roll_deg'], final_pitch_deg=final['pitch_deg'],
        additional_precision=final['additional_80um_0p5deg'], functional_plus_precision=success and final['additional_80um_0p5deg'],
        task_end_pose=analysis.precise(raw['trace'][task_index]), residual_audit=residual_audit,
        no_new_maximum_progress_active_s=no_progress_s,
        axial_stall_events=sum(e['reason'] == 'AXIAL_STALL' for e in raw['controller_events']),
        phase_times_s=phases, search_entries=sum(e['phase'] == 'SEARCH' for e in raw['controller_events']),
        unload_entries=sum(e['phase'] == 'UNLOAD' for e in raw['controller_events']),
        reference_problems=raw['reference_problems'], final_reason=raw['final_session']['reason'],
        control_cycles=raw['control_cycles'], physical_substeps=raw['physical_substeps'],
        policy_calls=raw['policy_calls'], optimizer_steps=raw['optimizer_steps'],
        audit_tail_s=raw['audit_end_time_s'] - raw['task_end_time_s'], wall_seconds=raw['wall_seconds'])


def main():
    if (OUT / 'assessment.json').exists(): raise FileExistsError('Preserve first result assessment')
    binding, config = c.verify_binding(); registration = c.read(OUT / 'registration.json')
    assert c.sha(OUT / 'grant.json') == registration['grant_sha256']
    ledger = c.read(PREP / 'execution/ledger.json'); closure = c.read(PREP / 'execution/authorization_closure.json')
    assert ledger['status'].startswith('CLOSED_') and closure['status'] == ledger['status']
    assert ledger['run_id'] == registration['run_id'] and ledger['grant_sha256'] == registration['grant_sha256']
    assert len(ledger['episodes']) <= 4 and closure['no_retry'] is True
    assert not (OUT / 'run').exists(); shutil.copytree(PREP / 'execution', OUT / 'run')
    records = []; incomplete = []
    for index, entry in enumerate(ledger['episodes']):
        supervisor = entry.get('supervisor', {})
        assert supervisor.get('process_exit_confirmed') is True and supervisor.get('owned_launcher_exit_confirmed') is True
        path = OUT / 'run' / ('case_' + str(index)) / 'episode.json.gz'
        if entry['status'] == 'finished' and path.exists():
            assert c.sha(path) == entry['archive_sha256']
            raw = json.loads(gzip.decompress(path.read_bytes()))
            row = record(raw, 'pure_B2', path, config); records.append(row)
            healthy = bool(row['physical_stopped'] and row['simulation_valid'] and not row['guard'] and
                           row['task_outcome'] in ('FULL_SUCCESS', 'TASK_FAILURE'))
            assert entry['healthy'] is healthy
        else: incomplete.append(dict(case_id=entry['case_id'], status=entry['status'], error=entry.get('error')))
    reuse = c.read(PREP / 'reuse_assessment.json')
    for item in reuse['rows']:
        path = Path(item['path']); assert c.sha(path) == item['sha256']
        raw = json.loads(gzip.decompress(path.read_bytes())); records.append(record(raw, item['role'], path, config))
    summaries = {}
    for role in ('pure_B2', 'F0', 'F2000'):
        rows = [r for r in records if r['role'] == role]
        summaries[role] = dict(available=len(rows), expected=4, functional_successes=sum(r['functional_success'] for r in rows),
            valid_stopped=sum(r['simulation_valid'] and r['physical_stopped'] for r in rows),
            guard_failures=sum(r['guard'] for r in rows), additional_precision_successes=sum(r['additional_precision'] for r in rows),
            functional_plus_precision_successes=sum(r['functional_plus_precision'] for r in rows),
            mean_penalized_time_s=math.fsum(r['penalized_time_s'] for r in rows) / 4 if len(rows) == 4 and all(r['penalized_time_s'] is not None for r in rows) else None,
            mean_final_xy_um=math.fsum(r['final_xy_um'] for r in rows) / len(rows) if rows else None,
            max_force_mN=max((r['force_mN'] for r in rows), default=None), max_torque_G_mNm=max((r['torque_G_mNm'] for r in rows), default=None))
        successful_times = sorted(r['task_time_s'] for r in rows if r['functional_success'])
        def quantile(q):
            if not successful_times: return None
            x = q * (len(successful_times) - 1); lo = math.floor(x); hi = math.ceil(x)
            return successful_times[lo] * (hi - x) + successful_times[hi] * (x - lo) if hi != lo else successful_times[lo]
        summaries[role].update(success_conditioned_mean_s=math.fsum(successful_times) / len(successful_times) if successful_times else None,
                               success_time_quantiles_s={str(q): quantile(q) for q in (.25, .5, .75)},
                               no_new_maximum_progress_active_s_total=math.fsum(r['no_new_maximum_progress_active_s'] for r in rows))
    b2_mean = summaries['pure_B2']['mean_penalized_time_s']
    costs = dict(claimed_attempts=len(ledger['episodes']), environment_creation_attempts=sum(e.get('environment_creation_attempted', 0) for e in ledger['episodes']),
        environments_created=sum(e.get('environment_created', 0) for e in ledger['episodes']), reset_attempts=sum(e.get('reset_attempted', 0) for e in ledger['episodes']),
        resets_completed=sum(e.get('reset_completed', 0) for e in ledger['episodes']), completed_archives=sum(r['role'] == 'pure_B2' for r in records),
        control_cycles=sum(e.get('control_cycles', 0) for e in ledger['episodes']), native_steps=sum(e.get('physical_substeps', 0) for e in ledger['episodes']),
        policy_calls=0, learner_constructions=0, tensor_loads=0, formal_updates=0, replay_publications=0,
        unused_closed=closure['unused_closed'], package_wall_s=(datetime.fromisoformat(ledger['ended_at']) - datetime.fromisoformat(ledger['started_at'])).total_seconds())
    result = dict(version='pure_b2_four_case_assessment_v1', assessed_at=c.now(), status=ledger['status'], records=records,
        incomplete=incomplete, summaries=summaries, costs=costs, cumulative_dynamic=254 + costs['reset_attempts'],
        relative_time_improvement_over_pure_B2={role: 1. - summaries[role]['mean_penalized_time_s'] / b2_mean if b2_mean else None for role in ('F0', 'F2000')},
        original_F2000_over_F0_improvement=1. - summaries['F2000']['mean_penalized_time_s'] / summaries['F0']['mean_penalized_time_s'],
        original_10percent_gate_passed=False, inherited_evaluations=8, new_independent_tests=0,
        automatic_tracking='PAUSED', training_admitted=False, full_B2_accepted=False, C_accepted=False,
        common_key=config['common_key'], source_binding_sha256=c.sha(PREP / 'source_binding.json'),
        analysis_sources={str(S21 / 'analyze.py'): c.sha(S21 / 'analyze.py'), str(OUT / 'assess_results.py'): c.sha(OUT / 'assess_results.py')},
        definitions=dict(time='Registered task_end_time; valid failures 26s, no complete mean if missing/invalid',
            precision='Supplemental 80um carrier XY / 0.5deg quaternion angle, unchanged functional labels',
            precision_time='Supplemental success uses audit-end pose; task-end pose is saved separately',
            residual_integrals='Absolute time-integrals over active task cycles: X/Y in metres, roll/pitch in radians; order X,Y,roll,pitch. Effective command delta is not physical causal displacement.',
            no_progress='INSERT/SEARCH time with no increase of clipped maximum Z advance above 1e-12m; diagnostic, not a new failure threshold',
            quantiles='Inclusive linear interpolation of successful task times, descriptive n=4, not a population estimate',
            data_use='Four used joint development points, one training seed, no statistical population claim'))
    c.verify_binding(); c.write(OUT / 'assessment.json', result)
    flat = []
    for row in records: flat.append({k: v for k, v in row.items() if type(v) in (str, int, float, bool) or v is None})
    with (OUT / 'comparison.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(flat[0])); writer.writeheader(); writer.writerows(flat)
    c.write(OUT / 'authorization_closure.json', closure)
    print(json.dumps(dict(status=result['status'], summaries=summaries, costs=costs,
        cumulative_dynamic=result['cumulative_dynamic'], time_improvement=result['relative_time_improvement_over_pure_B2']), ensure_ascii=False))


if __name__ == '__main__': main()
