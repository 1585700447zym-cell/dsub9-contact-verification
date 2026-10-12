"""Read-only physical evidence reconciliation after the one-shot process exits."""
import gzip
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(r'D:\dsub9项目计划\first_stage_sim\.worktrees\dsub9-v1-contact-validation')
OUT = ROOT/'deliverables/learning_chain/b2_rebound_execution_20261008'
SOURCE = ROOT/'deliverables/learning_chain/b2_preflight_rebound_20261008'
sys.path.insert(0, str(SOURCE))
from scope_contract import read, sha, proposal, attempt_specs
from run_preflight import check_binding, BINDING

ZERO_KEYS = ('learner_constructions','tensor_reads','network_forwards','optimizer_updates','replay_publications')

def write_new(path, value):
    with path.open('x',encoding='utf-8',newline='\n') as f:
        json.dump(value,f,ensure_ascii=False,indent=2); f.write('\n')

def main():
    assert not (OUT/'authorization_closure.json').exists()
    candidate,binding = check_binding()
    run = OUT/'run'; ledger = read(run/'ledger.json'); assessment = read(run/'assessment.json')
    pin = sha(OUT/'grant.json'); registration = read(OUT/'registration.json')
    assert pin == registration['grant_sha256'] == sha(run/'grant.json')
    assert ledger['status'].startswith('CLOSED_') and not any(e['status']=='running' for e in ledger['attempts'])
    claim = SOURCE/'claims'/pin; identity = read(claim/'identity.json'); closed = read(claim/'closed.json')
    assert identity['output'] == str(run) and closed['status'] == ledger['status']
    gate = Path(identity['outer_gate']); assert gate.is_relative_to(ROOT/'tmp/b2_scope_supervisors')
    outer = read(gate.with_suffix('.supervisor.json'))
    assert outer['process_exit_confirmed'], 'Cannot close without owned-process exit confirmation'
    copies = {}
    for origin, name in ((claim,'claim'),(gate.parent,'outer_supervisor')):
        target = OUT/'execution_evidence'/name; target.mkdir(parents=True,exist_ok=False)
        for path in origin.iterdir():
            if path.is_file():
                dest = target/path.name; assert not dest.exists(); shutil.copyfile(path,dest)
                copies[str(path)] = dict(copy=dest.relative_to(OUT).as_posix(),sha256=sha(dest))
    consumed = sorted(p.name for p in claim.iterdir() if p.is_dir() and p.name.endswith('.consumed'))
    totals = dict(case_environment_instances_attempted=0,case_environment_instances_completed=0,
                  reset_attempts=0,resets_completed=0,control_cycles=0,physical_substeps=0,
                  engine_processes_with_runtime_proof=0,**{k:0 for k in ZERO_KEYS})
    rows=[]; issues=[]
    for entry in ledger['attempts']:
        name=entry['id']; base=run/name
        archive=base.with_suffix('.json.gz')
        if not archive.exists():
            issues.append(name+': no complete raw; use retained partial/cost evidence and conservative ledger bounds')
            options=[base.with_suffix('.error.json.gz'),base.with_suffix('.partial.json.gz')]
            archive=next((p for p in options if p.exists()),None)
        raw=None
        if archive is not None:
            with gzip.open(archive,'rt',encoding='utf-8') as f: raw=json.load(f)
        costpath=base.with_suffix('.costs.json'); cost=read(costpath) if costpath.exists() else (raw or {}).get('costs',{})
        supervisor=read(base.with_suffix('.supervisor.json'))
        assert supervisor['process_exit_confirmed'], name
        for k in ZERO_KEYS: assert cost.get(k,0)==0, name+': '+k
        for k in ('case_environment_instances_attempted','case_environment_instances_completed','reset_attempts','resets_completed')+ZERO_KEYS:
            totals[k]+=cost.get(k,0)
        complete=archive == base.with_suffix('.json.gz')
        cycles=(raw or {}).get('control_cycles'); steps=(raw or {}).get('physical_substeps')
        if complete:
            assert raw['fault'] is None and raw['costs']==cost, name
            assert cost['native_step_calls']==steps==raw['guard_facts']['checked_substeps']==cycles*10, name
            totals['control_cycles']+=cycles; totals['physical_substeps']+=steps
            totals['engine_processes_with_runtime_proof']+=int(bool(raw['runtime_proof']))
        else:
            issues.append(name+': incomplete evidence not treated as exact final cost')
        if entry['status']=='finished':
            assert complete and sha(archive)==entry['archive_sha256']
            assert entry['physical_substeps_lower_bound']==entry['physical_substeps_upper_bound']==steps
        rows.append(dict(id=name,kind=entry['kind'],registered_status=entry['status'],
                         registered_audit_passed=entry['audit_passed'],complete_raw=complete,
                         archive=None if archive is None else archive.relative_to(OUT).as_posix(),
                         archive_sha256=None if archive is None else sha(archive),cycles=cycles,physical_substeps=steps,
                         wall_seconds=(raw or {}).get('wall_seconds'),supervisor_wall_seconds=supervisor.get('wall_seconds'),
                         process_exit_confirmed=supervisor['process_exit_confirmed'],costs=cost,
                         raw_reported_outcome=(raw or {}).get('outcome')))
    specs=attempt_specs(candidate)
    assert [e['id'] for e in ledger['attempts']]==[s['id'] for s in specs[:len(ledger['attempts'])]]
    assert len(assessment['static'])==9 and len(assessment['dynamic'])==16
    actual=dict(totals,static_initializations=ledger['static_attempts'],dynamic_attempts=ledger['dynamic_attempts'])
    complete_counts=all(r['complete_raw'] for r in rows)
    cumulative=209+ledger['dynamic_attempts']
    limits=candidate['proposed_limits']
    assert actual['dynamic_attempts']<=16 and actual['static_initializations']<=9
    assert actual['physical_substeps']<=limits['total_physical_substeps'] and actual['reset_attempts']<=25
    assert actual['case_environment_instances_attempted']<=25 and outer['wall_seconds']<=21630
    closure=dict(stage_id='B2-SCOPE-06',user_date='2026-10-08',status=ledger['status'],
                 grant_sha256=pin,binding_sha256=sha(BINDING),bound_files_verified=len(binding['files']),
                 original_ledger_sha256=sha(run/'ledger.json'),actual=actual,
                 exact_final_counts_reconciled=complete_counts,count_issues=issues,
                 original_ledger_step_bounds=[ledger['physical_substeps_lower_bound'],ledger['physical_substeps_upper_bound']],
                 cumulative_dynamic_before=209,cumulative_dynamic_after=cumulative,
                 unused_static_closed=ledger['unused_static_closed'],unused_dynamic_closed=ledger['unused_dynamic_closed'],
                 retry_allowed=False,old_budgets_reopened=False,process_exit_confirmed=True,
                 physical_stop_confirmation_basis='Bound worker/full-matrix raw STOP-tail audits and outcome.physical_stopped; supervisor physical_stop_confirmed is an unpopulated conservative placeholder, not stop evidence.',
                 whole_supervised_wall_seconds=outer['wall_seconds'],deadline_hit=outer.get('deadline_hit'),
                 registered_static_audit_passes=sum(r['audit_passed'] for r in assessment['static']),
                 registered_dynamic_audit_passes=sum(r['audit_passed'] for r in assessment['dynamic']),
                 functional_successes=sum(r.get('functional_success') is True for r in assessment['dynamic']),
                 strict_precision_successes=sum(r.get('strict_precision_success') is True for r in assessment['dynamic']),
                 original_assessment_route=assessment['route'],automatic_tracking='PAUSED',training_admitted=False,
                 full_B2_accepted=False,C_accepted=False,independent_tests=0,actual_attempts=rows,
                 evidence_copies=copies,consumed_claim_directories=consumed)
    write_new(OUT/'authorization_closure.json',closure)
    assert not any(k.split('.')[0] in {'numpy','mujoco','torch','stable_baselines3'} for k in sys.modules)
    with (OUT/'progress.md').open('a',encoding='utf-8') as f:
        f.write('\n一次执行结束：'+ledger['status']+'；累计动态'+str(cumulative)+'，路线'+assessment['route']+'；原档案和账本保持，未重试。\n')
    print(json.dumps({k:closure[k] for k in ('status','actual','cumulative_dynamic_after','original_assessment_route','whole_supervised_wall_seconds','unused_dynamic_closed')},ensure_ascii=False))

if __name__=='__main__': main()
