"""Exclusive stratified pure-B2 launch; no scientific imports before admission."""
import argparse
import importlib.abc
import json
import os
from pathlib import Path
import sys
import time
import uuid

OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT))
from scope_contract import ROOT,LIMITS,new_cases,read,write,sha,now,helper,require_grant,verify_binding,next_case,check_receipt_costs


class NoScience(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in ('numpy','mujoco','torch','gymnasium','stable_baselines3'):
            raise PermissionError('Scientific import before an owned admitted worker: '+fullname)


class NoLearning(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in ('torch','stable_baselines3') or fullname in (
            'tools.learning.v4_sac','tools.learning.sac_update','tools.learning.v4_checkpoint','tools.learning.sac_checkpoint'):
            raise PermissionError('Learning runtime forbidden in pure B2: '+fullname)


_guard=NoScience()
sys.meta_path.insert(0,_guard)


def checked_grant(args):
    if not args.grant or not args.grant_pin or not args.run_id:
        raise PermissionError('Separate explicit 21-case physical grant required')
    if sha(args.grant)!=args.grant_pin:raise PermissionError('Grant pin differs')
    grant=read(args.grant)
    if not isinstance(grant,dict):raise PermissionError('Explicit grant object required')
    require_grant(grant,grant.get('binding_sha256',''),args.run_id)
    if grant['binding_sha256']!=sha(OUT/'source_binding.json'):raise PermissionError('Source binding differs')
    binding,config=verify_binding()
    qualification=read(OUT/'qualification_candidate.json')
    if (qualification.get('source_binding_sha256')!=sha(OUT/'source_binding.json') or
        qualification.get('offline_checks_passed') is not True or qualification.get('fresh_review_completed') is not True):
        raise PermissionError('Bound offline verification and completed fresh review required')
    return grant,binding,config


def claim_worker(execution,args):
    index=args.case_index
    if type(index) is not int or not 0<=index<21:raise PermissionError('Registered new-case index required')
    run=Path(execution)/('case_'+str(index));launch=read(run/'launch.json');ledger=read(Path(execution)/'ledger.json')
    point=new_cases()[index]
    if (not args.gate or Path(args.gate).resolve()!=(run/'gate').resolve() or
        launch!=dict(run_id=args.run_id,nonce=args.nonce,case_index=index,case_id=point['id']) or
        ledger.get('run_id')!=args.run_id or ledger.get('grant_sha256')!=args.grant_pin or
        ledger.get('status')!='RUNNING' or len(ledger['episodes'])!=index+1 or
        ledger['episodes'][-1].get('case_id')!=point['id'] or ledger['episodes'][-1].get('status')!='claimed' or
        ledger['episodes'][-1].get('nonce')!=args.nonce or
        next_case(ledger['episodes'][:-1])!=point):
        raise PermissionError('Worker gate or exclusively reserved case identity differs')
    with (run/'worker.claim').open('x',encoding='utf-8') as stream:
        json.dump(dict(pid=os.getpid(),nonce=args.nonce,case_id=point['id']),stream);stream.flush();os.fsync(stream.fileno())
    return run,point


def collect_receipt(ledger,run):
    path=Path(run)/'receipt.json'
    if path.exists():
        receipt=read(path)
        if receipt['case_id']!=ledger['episodes'][-1]['case_id']:raise ValueError('Receipt case differs from charged reservation')
        check_receipt_costs(receipt)
        ledger['episodes'][-1]=dict(receipt,receipt_path=str(path),receipt_sha256=sha(path))
    supervisor=Path(run)/'gate.supervisor.json'
    if supervisor.exists():ledger['episodes'][-1]['supervisor']=read(supervisor)


def reconcile_attempts(ledger,execution,package_proof):
    """Recover already-written evidence after the externally owned tree exits."""
    for index,original in enumerate(ledger['episodes']):
        run=Path(execution)/('case_'+str(index));holder=dict(episodes=[dict(original)])
        path=run/'receipt.json'
        try:
            collect_receipt(holder,run);row=holder['episodes'][0]
        except (ValueError,KeyError,TypeError,OSError) as exc:
            row=dict(original,healthy=False,receipt_reconciliation_error=repr(exc),
                     retained_receipt_path=str(path),operation_counts_known=False)
            if path.exists():row['retained_receipt_sha256']=sha(path)
        row['package_tree_exit_confirmed']=package_proof.get('process_exit_confirmed') is True
        if path.exists() and 'receipt_reconciliation_error' not in row:
            row['operation_counts_known']=all(type(row.get(k)) is int for k in
                ('environment_creation_attempted','environment_created','reset_attempted','reset_completed'))
            complete=row.get('status') in ('finished','error') and row['operation_counts_known'] and all(
                type(row.get(k)) is int for k in ('control_cycles','physical_substeps'))
            row['receipt_costs_complete']=complete and row['package_tree_exit_confirmed']
            row['control_count_evidence']='complete' if row['receipt_costs_complete'] else 'lower_bound'
        elif row.get('supervisor',{}).get('go_issued') is False and row['package_tree_exit_confirmed']:
            row.update(operation_counts_known=True,receipt_costs_complete=True,control_count_evidence='not_started',
                environment_creation_attempted=0,environment_created=0,reset_attempted=0,reset_completed=0,
                control_cycles=0,physical_substeps=0)
        else:
            row.update(operation_counts_known=False,receipt_costs_complete=False,control_count_evidence='unknown')
        ledger['episodes'][index]=row
    return ledger


def worker(args):
    _,binding,config=checked_grant(args)
    expected=OUT/'execution'/('case_'+str(args.case_index))/'gate'
    if not args.gate or Path(args.gate).resolve()!=expected.resolve():raise PermissionError('Unregistered worker gate')
    helper('supervised').enter_gate(args.gate,args.parent_pid,args.registered_at)
    run,point=claim_worker(OUT/'execution',args)
    verify_binding()
    sys.meta_path.remove(_guard);sys.meta_path.insert(0,NoLearning());sys.path.insert(0,str(ROOT))
    from baseline_rollout import physical_case
    receipt=dict(case_id=point['id'],attempt_index=args.case_index,matrix_index=config['cases'].index(point),
        status='running',healthy=False,environment_creation_attempted=0,environment_created=0,
        reset_attempted=0,reset_completed=0,control_cycles=0,physical_substeps=0,policy_calls=0,
        formal_updates=0,learner_constructions=0,tensor_loads=0,replay_publications=0)
    write(run/'receipt.json',receipt)
    physical_case(config,point,args.case_index,run,receipt,binding)


def worker_command(binding,args,index,nonce):
    return [binding['executable'],'-I','-X','utf8','-X','faulthandler','-B',str(OUT/'baseline_entry.py'),
        '--worker','--case-index',str(index),'--grant',str(Path(args.grant).resolve()),'--grant-pin',args.grant_pin,
        '--run-id',args.run_id,'--nonce',nonce]


def close(execution,ledger):
    ledger.update(ended_at=now(),unused_closed=21-len(ledger['episodes']),
        claimed_attempts=len(ledger['episodes']),new_budget_reusable=False,automatic_tracking='PAUSED')
    write(execution/'ledger.json',ledger)
    write(execution/'authorization_closure.json',dict(status=ledger['status'],grant_sha256=ledger['grant_sha256'],
        claimed_attempts=ledger['claimed_attempts'],unused_closed=ledger['unused_closed'],no_retry=True,
        automatic_tracking='PAUSED',cumulative_before=258))


def coordinator(args):
    _,binding,config=checked_grant(args)
    execution=OUT/'execution'
    if not args.gate or Path(args.gate).resolve()!=(execution/'coordinator_gate').resolve():
        raise PermissionError('Unregistered package gate')
    helper('supervised').enter_gate(args.gate,args.parent_pid,args.registered_at)
    launch=read(execution/'coordinator_launch.json');ledger=read(execution/'ledger.json')
    if launch!=dict(run_id=args.run_id,nonce=args.nonce,grant_sha256=args.grant_pin) or ledger['status']!='RESERVED':
        raise PermissionError('Package reservation identity differs')
    with (execution/'coordinator.claim').open('x',encoding='utf-8') as stream:stream.write(args.nonce)
    ledger['status']='RUNNING';write(execution/'ledger.json',ledger)
    started=time.monotonic()
    try:
        for index,point in enumerate(new_cases()):
            verify_binding()
            if next_case(ledger['episodes'])!=point:break
            if (OUT/'STOP').exists():raise RuntimeError('STOP requested; no new attempt')
            remaining=LIMITS['whole_wall_s']-(time.monotonic()-started)
            if remaining<=0:raise TimeoutError('Whole package deadline')
            run=execution/('case_'+str(index));run.mkdir(exist_ok=False);nonce=uuid.uuid4().hex
            ledger['episodes'].append(dict(case_id=point['id'],status='claimed',healthy=False,nonce=nonce))
            write(execution/'ledger.json',ledger)
            write(run/'launch.json',dict(run_id=args.run_id,nonce=nonce,case_index=index,case_id=point['id']))
            try:helper('supervised').bounded_process(worker_command(binding,args,index,nonce),run/'gate',min(1200,remaining))
            finally:collect_receipt(ledger,run);write(execution/'ledger.json',ledger)
            if next_case(ledger['episodes']) is None:break
        ledger['status']='CLOSED_COMPLETE' if len(ledger['episodes'])==21 and all(
            __import__('scope_contract').receipt_healthy(r) for r in ledger['episodes']) else 'CLOSED_EARLY'
    except BaseException as exc:
        ledger.update(status='CLOSED_ERROR',error=repr(exc));raise
    finally:close(execution,ledger)


def execute(args):
    _,binding,config=checked_grant(args)
    if os.name!='nt':raise OSError('Qualified Windows job supervision required')
    # Source inspection above is pre-launch. The complete scientific coordinator,
    # per-case hashing, initialization, serialization and child exit are externally timed.
    execution=OUT/'execution';execution.mkdir(exist_ok=False)
    ledger=dict(version='b2_stratified_zero_ledger_v1',status='RESERVED',run_id=args.run_id,
        grant_sha256=args.grant_pin,matrix_scope_key=config['common_key'],shared_common_key=config['parent_common_key'],
        episodes=[],limits=LIMITS,cumulative_before=258,independent_tests=0,started_at=now())
    write(execution/'ledger.json',ledger);nonce=uuid.uuid4().hex
    write(execution/'coordinator_launch.json',dict(run_id=args.run_id,nonce=nonce,grant_sha256=args.grant_pin))
    command=worker_command(binding,args,0,nonce)
    index=command.index('--worker');command[index]='--coordinator';del command[index+1:index+3]
    try:helper('supervised').bounded_process(command,execution/'coordinator_gate',LIMITS['whole_wall_s'])
    finally:
        ledger=read(execution/'ledger.json')
        supervision=execution/'coordinator_gate.supervisor.json'
        proof=read(supervision) if supervision.exists() else {}
        ledger['package_supervisor']=proof
        reconcile_attempts(ledger,execution,proof)
        if ledger['status'] not in ('CLOSED_COMPLETE','CLOSED_EARLY','CLOSED_ERROR') or not (
            proof.get('process_exit_confirmed') is True and proof.get('owned_launcher_exit_confirmed') is True and proof.get('returncode')==0):
            ledger.update(status='CLOSED_ERROR',error='Package exit or coordinator close not confirmed')
        close(execution,ledger)


def main():
    parser=argparse.ArgumentParser()
    mode=parser.add_mutually_exclusive_group(required=True)
    for name in ('check','execute','worker','coordinator'):mode.add_argument('--'+name,action='store_true')
    for name in ('grant','grant-pin','run-id','nonce'):parser.add_argument('--'+name)
    parser.add_argument('--case-index',type=int)
    parser.add_argument('gate',nargs='?');parser.add_argument('parent_pid',nargs='?',type=int);parser.add_argument('registered_at',nargs='?',type=float)
    args=parser.parse_args()
    if args.check:
        binding,config=verify_binding()
        print(json.dumps(dict(source_binding_verified=True,new_case_ids=[p['id'] for p in new_cases()],
            matrix_scope_key=config['common_key'],scientific_execution_admitted=False,training_admitted=False)))
    elif args.worker:worker(args)
    elif args.coordinator:coordinator(args)
    else:execute(args)


if __name__=='__main__':main()
