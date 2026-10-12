"""Read and copy finished execution evidence. No backend imports or reruns."""
from pathlib import Path
import gzip
import json
import shutil
import sys
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
RUNNER=OUT.parent/'b2_joint_admission_preflight_20261009'
sys.path.insert(0,str(RUNNER))
from scope_contract import read,sha,proposal,attempt_specs
from execution_contract import write

def main():
    if (OUT/'authorization_closure.json').exists():raise PermissionError('Closeout already captured')
    reg=read(OUT/'registration.json');pin=reg['grant_sha256'];claim=RUNNER/'claims'/pin
    identity=read(claim/'identity.json');gate=Path(identity['outer_gate'])
    supervisor=read(gate.with_suffix('.supervisor.json'))
    if supervisor.get('process_exit_confirmed') is not True:raise RuntimeError('Owned process tree exit unconfirmed')
    ledger=read(OUT/'run/ledger.json')
    if ledger['status']=='OPEN' or any(r['status']=='running' for r in ledger['attempts']):raise RuntimeError('Execution still open')
    closed=read(claim/'closed.json');copies={}
    def copy(source,relative):
        source=Path(source);dst=OUT/relative;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dst)
        copies[str(source)]=dict(copy=relative,sha256=sha(dst))
    for p in claim.iterdir():
        if p.is_file():copy(p,'execution_evidence/claim/'+p.name)
    for suffix in ('.supervisor.json','.ready.json','.go.json','.log'):
        p=gate.with_suffix(suffix)
        if p.exists():copy(p,'execution_evidence/outer'+suffix)
    rows=[];totals={};counts=dict(native_steps=0,control_cycles=0,observation_vectors=0)
    for entry in ledger['attempts']:
        base=OUT/'run'/entry['id'];archives=[]
        for suffix in ('.json.gz','.error.json.gz','.partial.json.gz'):
            p=base.with_suffix(suffix)
            if p.exists():archives.append(p)
        row=dict(id=entry['id'],status=entry['status'],audit_passed=entry.get('audit_passed',False),
            ledger_outcome=entry.get('outcome'),error=entry.get('error'),raw_archives=[p.name for p in archives])
        raw=None
        if archives:
            # Prefer final, else exception, else latest checkpoint. Never turn a
            # partial checkpoint into a completed outcome or audited success.
            raw=json.loads(gzip.decompress(archives[0].read_bytes()))
            row.update(raw_source=archives[0].name,raw_sha256=sha(archives[0]),raw_fault=raw.get('fault'),
                raw_outcome=raw.get('outcome'),final_session=raw.get('final_session'),
                peak_loads=raw.get('peaks'),guard_facts=raw.get('guard_facts'),
                physical_substeps=raw.get('physical_substeps',0),control_cycles=raw.get('control_cycles',0),
                observed_vectors=len(raw.get('observations',[])),worker_wall_seconds=raw.get('wall_seconds'),
                events=raw.get('events',[]),fixture_count=len(raw.get('fixture_events',[])),
                recovery_transitions=[dict(cycle_id=r['cycle_id'],signature=r['signature'],reason=r['reason']) for r in raw.get('recovery_transitions',[])])
            counts['native_steps']+=row['physical_substeps'];counts['control_cycles']+=row['control_cycles'];counts['observation_vectors']+=row['observed_vectors']
        costs=read(base.with_suffix('.costs.json')) if base.with_suffix('.costs.json').exists() else (raw or {}).get('costs',{})
        row['costs']=costs
        for key,value in costs.items():totals[key]=totals.get(key,0)+value
        audit=base.with_suffix('.audit.json')
        if audit.exists():row['assessment']=read(audit)['assessment']
        rows.append(row)
        del raw
    consumed=sorted(p.name for p in claim.iterdir() if p.is_dir() and p.name.endswith('.consumed'))
    reserved=ledger['dynamic_attempts']
    summary=dict(stage_id='B2-SCOPE-10',status='EXECUTION_CLOSED',ledger_status=ledger['status'],
        planned_dynamic=12,reserved_dynamic=reserved,actual_environment_creations=totals.get('case_environment_instances_attempted',0),
        completed_resets=totals.get('resets_completed',0),audited_attempts=sum(r['audit_passed'] for r in rows),
        cumulative_before=225,cumulative_after_reserved=225+reserved,unused_dynamic_closed=12-reserved,
        learning_costs={k:totals.get(k,0) for k in ('learner_constructions','tensor_reads','network_forwards','optimizer_updates','replay_publications')},
        cost_totals=totals,recorded_counts=counts,rows=rows,
        outer_supervisor=supervisor,outer_process_exit_confirmed=True,
        raw_physical_stop_is_independent_of_process_exit=True,training_admitted=False,full_B2_accepted=False,C_accepted=False,
        automatic_tracking='PAUSED',retry_allowed=False)
    assessment=OUT/'run/assessment.json'
    if assessment.exists():summary['matrix_assessment']=read(assessment)
    closure=dict(stage_id='B2-SCOPE-10',status='CLOSED_NO_RETRY',grant_sha256=pin,claim_closed_record=closed,
        scope_consumed=(RUNNER/'claims/scope.consumed').is_dir(),consumed_claim_directories=consumed,
        reserved_dynamic=reserved,unused_dynamic_closed=12-reserved,static_attempts=ledger['static_attempts'],
        evidence_copies=copies,training_admitted=False,retry_allowed=False)
    write(OUT/'execution_summary.json',summary);write(OUT/'authorization_closure.json',closure)
    print(json.dumps(dict(status='CLOSED',reserved=reserved,audited=summary['audited_attempts'],unused_closed=12-reserved,
        cumulative=225+reserved,cost_totals=totals,recorded_counts=counts),ensure_ascii=False))
if __name__=='__main__':main()
