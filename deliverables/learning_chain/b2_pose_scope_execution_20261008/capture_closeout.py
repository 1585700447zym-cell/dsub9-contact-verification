"""Reconcile closed one-shot costs and preserve supervisor evidence; no runtime loads."""
import json
from pathlib import Path
import sys

ROOT = Path(r'D:\dsub9项目计划\first_stage_sim\.worktrees\dsub9-v1-contact-validation')
OUT = Path(__file__).resolve().parent
SOURCE = ROOT / 'deliverables/learning_chain/b2_pose_scope_preflight_20261008'
sys.path.insert(0, str(SOURCE))
from scope_contract import read, sha
from run_preflight import check_binding, BINDING
from assess import read_archive

def write_new(path, data):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write('\n')

def main():
    assert OUT == ROOT / 'deliverables/learning_chain/b2_pose_scope_execution_20261008'
    _, binding = check_binding()
    run = OUT / 'run'
    ledger = read(run / 'ledger.json')
    assessment = read(run / 'assessment.json')
    grant_pin = sha(OUT / 'grant.json')
    assert grant_pin == 'ccf21cb187103a504009cfa4ea9a3a73cc8b4b61869345e269321430847a698a'
    assert sha(run / 'grant.json') == grant_pin
    claim = SOURCE / 'claims' / grant_pin
    identity = read(claim / 'identity.json')
    closed = read(claim / 'closed.json')
    assert ledger['status'] == closed['status'] == 'CLOSED_SUPERVISOR_ERROR'
    assert (ledger['static_attempts'], ledger['dynamic_attempts'], ledger['unused_dynamic_closed']) == (9, 1, 15)
    assert identity['output'] == str(run)
    gate = Path(identity['outer_gate'])
    assert gate.is_relative_to(ROOT / 'tmp/b2_scope_supervisors')
    outer = read(gate.with_suffix('.supervisor.json'))
    assert outer['process_exit_confirmed'] and outer['owned_launcher_exit_confirmed']
    assert not outer['deadline_hit']
    copies = {}
    for origin, subfolder in [(claim, 'claim'), (gate.parent, 'outer_supervisor')]:
        target = OUT / 'execution_evidence' / subfolder
        target.mkdir(parents=True, exist_ok=False)
        for source in origin.iterdir():
            if source.is_file():
                dest = target / source.name
                with dest.open('xb') as stream:
                    stream.write(source.read_bytes())
                copies[str(source)] = dict(copy=dest.relative_to(OUT).as_posix(), sha256=sha(dest))
    consumed = sorted(p.name for p in claim.iterdir() if p.is_dir() and p.name.endswith('.consumed'))
    assert len(consumed) == 10
    actual = dict(engine_processes_with_runtime_proof=0, case_environment_instances=0,
        resets=0, static_initializations=9, dynamic_attempts=1, control_cycles=0, physical_substeps=0,
        learner_constructions=0, tensor_reads=0, network_forwards=0, optimizer_updates=0, replay_publications=0)
    rows = []
    for entry in ledger['attempts']:
        name = entry['id']
        archive = run / (name + '.json.gz')
        raw = read_archive(archive)
        cost = read(run / (name + '.costs.json'))
        supervisor = read(run / (name + '.supervisor.json'))
        assert supervisor['process_exit_confirmed']
        assert raw['costs'] == cost and raw['fault'] is None
        assert cost['native_step_calls'] == raw['physical_substeps'] == raw['guard_facts']['checked_substeps']
        assert raw['physical_substeps'] == raw['control_cycles'] * 10
        assert cost['resets_completed'] == cost['reset_attempts'] == 1
        assert cost['case_environment_instances_completed'] == cost['case_environment_instances_attempted'] == 1
        assert raw['runtime_proof']
        actual['engine_processes_with_runtime_proof'] += 1
        actual['case_environment_instances'] += 1
        actual['resets'] += 1
        actual['control_cycles'] += raw['control_cycles']
        actual['physical_substeps'] += raw['physical_substeps']
        for key in ('learner_constructions', 'tensor_reads', 'network_forwards', 'optimizer_updates', 'replay_publications'):
            assert cost[key] == 0
            actual[key] += cost[key]
        rows.append(dict(id=name, kind=entry['kind'], registered_status=entry['status'],
            registered_audit_passed=entry['audit_passed'], archive_sha256=sha(archive),
            cycles=raw['control_cycles'], physical_substeps=raw['physical_substeps'],
            wall_seconds=raw['wall_seconds'], supervisor_wall_seconds=supervisor['wall_seconds'],
            process_exit_confirmed=True, raw_reported_outcome=raw['outcome']))
    diagnosis = read(OUT / 'audit_diagnosis.json')
    assert diagnosis['counterfactual']['status'] == 'DIAGNOSTIC_AUDIT_PASSED_AFTER_SCALAR_TYPE_NORMALIZATION'
    assert rows[-1]['archive_sha256'] == diagnosis['original_archive_sha256']
    assert (actual['control_cycles'], actual['physical_substeps']) == (3045, 30450)
    assert sum(r['audit_passed'] for r in assessment['static']) == 9
    assert assessment['route'] == 'NO_SCOPE_QUALIFICATION'
    assert sum(r['status'] == 'NOT_ATTEMPTED' for r in assessment['dynamic']) == 15
    report = dict(stage_id='B2-SCOPE-03', user_date='2026-10-08', status='CLOSED_AUDIT_ERROR',
        grant_sha256=grant_pin, binding_sha256=sha(BINDING), bound_files_verified=len(binding['files']),
        actual=actual, cumulative_dynamic_before=208, cumulative_dynamic_after=209,
        unused_static_closed=0, unused_dynamic_closed=15, retry_allowed=False,
        original_ledger_status=ledger['status'], original_ledger_sha256=sha(run / 'ledger.json'),
        original_ledger_step_bounds=[ledger['physical_substeps_lower_bound'], ledger['physical_substeps_upper_bound']],
        reconciled_exact_substeps=30450,
        exact_count_basis='Complete archived raw, native-step counter, guard checked_substeps and 3045*10 agree; original conservative ledger is untouched.',
        registered_dynamic_audit_passes=0, registered_static_audit_passes=9,
        diagnostic_only_audit_passes=1, accepted_dynamic_scope=False,
        original_assessment_route=assessment['route'], process_exit_confirmed=True,
        whole_supervised_wall_seconds=outer['wall_seconds'], deadline_hit=False,
        automatic_tracking='PAUSED', training_admitted=False, full_B2_accepted=False, C_accepted=False,
        independent_tests=0, old_budgets_reopened=False, actual_attempts=rows,
        evidence_copies=copies, consumed_claim_directories=consumed,
        next_route='OFFLINE_COMPARATOR_REPAIR_AND_REAL_ARCHIVE_REGRESSION_BEFORE_ANY_FRESH_PHYSICAL_REGISTRATION')
    write_new(OUT / 'authorization_closure.json', report)
    assert not any(k.split('.')[0] in {'mujoco', 'torch', 'numpy', 'stable_baselines3'} for k in sys.modules)
    print(json.dumps(dict(status=report['status'], actual=actual, cumulative_dynamic=209,
        unused_dynamic_closed=15, supervised_wall_s=outer['wall_seconds'], bound_files=len(binding['files'])), ensure_ascii=False))

if __name__ == '__main__':
    main()
