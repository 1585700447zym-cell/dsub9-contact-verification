"""Exclusive numeric / frozen actor entry; parent and coordinator are stdlib only."""
import argparse,importlib.abc,json,os,sys,time,uuid
from pathlib import Path
OUT=Path(__file__).resolve().parent;sys.path.insert(0,str(OUT))
sys.modules['sac_entry']=sys.modules[__name__]
from sac_scope import (ROOT,read,write,sha,now,helper,verify_binding,require_grant,require_numeric,schedule,next_unit,
    receipt_healthy,check_receipt_costs,dynamic_precheck,PHYSICAL_LIMITS,NUMERIC_LIMITS)

class NoScience(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in ('numpy','torch','mujoco','gymnasium','stable_baselines3'):
            raise PermissionError('Scientific import before an owned admitted worker: '+fullname)

class NoTraining(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname in ('tools.learning.v4_sac','tools.learning.v4_checkpoint','tools.learning.v4_pilot_chain',
            'tools.learning.sac_update','tools.learning.sac_checkpoint'):
            raise PermissionError('Learner/chain/checkpoint restore forbidden in frozen evaluation: '+fullname)

_guard=NoScience();sys.meta_path.insert(0,_guard);_owned=None

def assert_owned():
    if _owned is None:raise PermissionError('No exclusively claimed admitted scientific worker')
    run,nonce=_owned;claim=read(run/'worker.claim')
    if claim.get('pid')!=os.getpid() or claim.get('nonce')!=nonce:raise PermissionError('Owned worker claim differs')

def checked_grant(args):
    if args.kind not in ('numeric','physical') or not args.grant or not args.grant_pin or not args.run_id:
        raise PermissionError('Separate explicit numeric/physical grant required')
    if sha(args.grant)!=args.grant_pin:raise PermissionError('Grant file pin differs')
    g=read(args.grant);require_grant(g,args.kind,sha(OUT/'source_binding.json'),args.run_id)
    binding,config=verify_binding();q=read(OUT/'qualification_candidate.json')
    if not (q.get('source_binding_sha256')==sha(OUT/'source_binding.json') and q.get('offline_checks_passed') is True and
        q.get('fresh_review_completed') is True and q.get('runtime_entry_implemented') is True):
        raise PermissionError('Bound offline checks and fresh review required')
    # Qualification and entry code are frozen in the final preparation seal.
    manifest=read(OUT/'delivery_manifest.json')
    for rel,pin in manifest['files'].items():
        if sha(OUT/rel)!=(pin['sha256'] if isinstance(pin,dict) else pin):raise PermissionError('Preparation seal changed: '+rel)
    if args.kind=='physical':require_numeric(g.get('numeric_result_sha256'))
    return g,binding,config

def limits(kind):return NUMERIC_LIMITS if kind=='numeric' else PHYSICAL_LIMITS

def directory(kind):return OUT/('numeric_execution' if kind=='numeric' else 'evaluation_execution')

def command(binding,args,mode,nonce,index=None):
    result=[binding['executable'],'-I','-X','utf8','-X','faulthandler','-B',str(OUT/'sac_entry.py'),
        '--'+mode,'--kind',args.kind,'--grant',str(Path(args.grant).resolve()),'--grant-pin',args.grant_pin,
        '--run-id',args.run_id,'--nonce',nonce]
    if index is not None:result+=['--case-index',str(index)]
    return result

def claim(run,args,expected):
    if not args.gate or Path(args.gate).resolve()!=(run/'gate').resolve():raise PermissionError('Unregistered worker gate')
    helper('supervised').enter_gate(args.gate,args.parent_pid,args.registered_at)
    if read(run/'launch.json')!=expected:raise PermissionError('Owned launch identity differs')
    with (run/'worker.claim').open('x',encoding='utf-8') as f:
        json.dump(dict(pid=os.getpid(),nonce=args.nonce),f);f.flush();os.fsync(f.fileno())

def worker(args):
    global _owned
    g,binding,cfg=checked_grant(args);execution=directory(args.kind)
    ledger=read(execution/'ledger.json')
    if ledger['run_id']!=args.run_id or ledger['grant_sha256']!=args.grant_pin:raise PermissionError('Reserved worker ledger differs')
    if args.kind=='numeric':
        if args.case_index is not None or ledger['status']!='RESERVED':raise PermissionError('Numeric slot already used')
        run=execution;claim(run,args,dict(run_id=args.run_id,nonce=args.nonce,grant_sha256=args.grant_pin))
    else:
        i=args.case_index
        if type(i) is not int or not 0<=i<42:raise PermissionError('Exact frozen unit index required')
        unit=schedule()[i];run=execution/('case_'+str(i))
        if (ledger['status']!='RUNNING' or len(ledger['episodes'])!=i+1 or
            ledger['episodes'][-1]!=dict(index=i,case_id=unit['case_id'],role=unit['role'],status='claimed',healthy=False,nonce=args.nonce) or
            next_unit(ledger['episodes'][:-1])!=unit):raise PermissionError('Exclusive physical reservation or prior gate differs')
        claim(run,args,dict(run_id=args.run_id,nonce=args.nonce,index=i,case_id=unit['case_id'],role=unit['role']))
    verify_binding()
    if not sys.flags.isolated or Path(sys.executable).resolve()!=Path(binding['executable']).resolve():raise PermissionError('Frozen isolated CPU interpreter required')
    _owned=(run,args.nonce);sys.meta_path.remove(_guard);sys.meta_path.insert(0,NoTraining());sys.path.insert(0,str(ROOT))
    if args.kind=='numeric':
        ledger['status']='RUNNING';write(execution/'ledger.json',ledger)
        meter=dict(numeric=True,status='running',tensor_load_attempts=0,tensor_loads=0,actor_construction_attempts=0,
            actor_constructions=0,reference_learner_construction_attempts=0,reference_learner_constructions=0,
            policy_call_attempts=0,policy_calls=0,formal_updates=0,optimizer_steps=0,replay_publications=0,native_steps=0,
            run_id=args.run_id,grant_sha256=args.grant_pin,nonce=args.nonce,binding_sha256=sha(OUT/'source_binding.json'),worker_pid=os.getpid())
        write(run/'receipt.json',meter)
        try:
            from actor_runtime import numeric_worker
            result=numeric_worker(run,cfg,binding,meter)
            result.update(run_id=args.run_id,grant_sha256=args.grant_pin,nonce=args.nonce,worker_pid=os.getpid())
            write(run/'result.json',result)
            meter['status']='finished';write(run/'receipt.json',meter);ledger['status']='CLOSED_COMPLETE'
        except BaseException as exc:
            meter.update(status='error',error=repr(exc));write(run/'receipt.json',meter);ledger.update(status='CLOSED_ERROR',error=repr(exc));raise
        finally:write(run/'ledger.json',ledger)
    else:
        receipt=dict(index=i,case_id=unit['case_id'],role=unit['role'],status='running',healthy=False,
            environment_creation_attempted=0,environment_created=0,reset_attempted=0,reset_completed=0,
            control_cycles=0,physical_substeps=0,policy_calls=0,policy_call_attempts=0,actor_construction_attempts=0,
            actor_constructions=0,tensor_load_attempts=0,tensor_loads=0,learner_constructions=0,formal_updates=0,replay_publications=0)
        write(run/'receipt.json',receipt)
        from sac_rollout import physical_case
        physical_case(cfg,unit,run,receipt,binding)

def collect(ledger,run):
    p=run/'receipt.json'
    if p.exists():
        r=read(p);original=ledger['episodes'][-1]
        if any(r.get(k)!=original[k] for k in ('index','case_id','role')):raise ValueError('Receipt identity differs from reservation')
        check_receipt_costs(r);ledger['episodes'][-1]=dict(r,receipt_path=str(p),receipt_sha256=sha(p))
    supervisor=run/'gate.supervisor.json'
    if supervisor.exists():ledger['episodes'][-1]['supervisor']=read(supervisor)

def close(execution,ledger):
    kind=ledger['kind'];ledger.update(ended_at=now(),automatic_tracking='PAUSED',new_budget_reusable=False,retries=0)
    if kind=='physical':
        ledger.update(claimed_attempts=len(ledger['episodes']),unused_closed=42-len(ledger['episodes']),dynamic_precheck=dynamic_precheck(ledger['episodes']))
    else:ledger.update(claimed_attempts=1,unused_closed=True)
    write(execution/'ledger.json',ledger)
    write(execution/'authorization_closure.json',dict(status=ledger['status'],kind=kind,run_id=ledger['run_id'],
        grant_sha256=ledger['grant_sha256'],unused_closed=ledger['unused_closed'],no_retry=True,old_budget_closed=True,
        automatic_tracking='PAUSED',cumulative_before=279))

def coordinator(args):
    _,binding,cfg=checked_grant(args)
    if args.kind!='physical':raise PermissionError('Numeric run has no coordinator')
    execution=directory(args.kind)
    if not args.gate or Path(args.gate).resolve()!=(execution/'package_gate').resolve():raise PermissionError('Unregistered coordinator gate')
    helper('supervised').enter_gate(args.gate,args.parent_pid,args.registered_at)
    ledger=read(execution/'ledger.json')
    if ledger['status']!='RESERVED' or read(execution/'launch.json')!=dict(run_id=args.run_id,nonce=args.nonce,grant_sha256=args.grant_pin):
        raise PermissionError('Coordinator reservation differs')
    with (execution/'coordinator.claim').open('x',encoding='utf-8') as f:f.write(args.nonce)
    ledger['status']='RUNNING';write(execution/'ledger.json',ledger);started=time.monotonic()
    try:
        for unit in schedule():
            if next_unit(ledger['episodes'])!=unit:break
            verify_binding()
            if (OUT/'STOP').exists():raise RuntimeError('STOP; no new physical attempt')
            remaining=21600-(time.monotonic()-started)
            if remaining<=0:raise TimeoutError('Whole package deadline')
            i=unit['index'];nonce=uuid.uuid4().hex;run=execution/('case_'+str(i));run.mkdir(exist_ok=False)
            ledger['episodes'].append(dict(index=i,case_id=unit['case_id'],role=unit['role'],status='claimed',healthy=False,nonce=nonce))
            write(execution/'ledger.json',ledger);write(run/'launch.json',dict(run_id=args.run_id,nonce=nonce,index=i,case_id=unit['case_id'],role=unit['role']))
            try:helper('supervised').bounded_process(command(binding,args,'worker',nonce,i),run/'gate',min(1200,remaining))
            finally:collect(ledger,run);write(execution/'ledger.json',ledger)
            if i==11:write(execution/'dynamic_precheck.json',dynamic_precheck(ledger['episodes']))
        ledger['status']='CLOSED_COMPLETE' if len(ledger['episodes'])==42 and all(receipt_healthy(r) for r in ledger['episodes']) and dynamic_precheck(ledger['episodes'])['passed'] else 'CLOSED_EARLY'
    except BaseException as exc:ledger.update(status='CLOSED_ERROR',error=repr(exc));raise
    finally:close(execution,ledger)

def reconcile(ledger,execution,proof):
    for i,original in enumerate(ledger['episodes']):
        run=execution/('case_'+str(i));holder=dict(episodes=[dict(original)])
        try:collect(holder,run);row=holder['episodes'][0]
        except (ValueError,KeyError,TypeError,OSError) as exc:row=dict(original,healthy=False,receipt_reconciliation_error=repr(exc))
        row['package_tree_exit_confirmed']=proof.get('process_exit_confirmed') is True
        receipt=run/'receipt.json'
        complete=receipt.exists() and 'receipt_reconciliation_error' not in row and row.get('status') in ('finished','error') and all(
            type(row.get(k)) is int for k in ('environment_creation_attempted','environment_created','reset_attempted','reset_completed','control_cycles','physical_substeps'))
        row['receipt_costs_complete']=bool(complete and row['package_tree_exit_confirmed'])
        row['control_count_evidence']='complete' if row['receipt_costs_complete'] else 'unknown_or_lower_bound'
        if not receipt.exists() and row.get('supervisor',{}).get('go_issued') is False and row['package_tree_exit_confirmed']:
            row.update(receipt_costs_complete=True,control_count_evidence='not_started',environment_creation_attempted=0,
                environment_created=0,reset_attempted=0,reset_completed=0,control_cycles=0,physical_substeps=0)
        ledger['episodes'][i]=row

def numeric_exit_proof(run,ledger,raw):
    """Bind the unchanged old supervisor to this single numeric run and worker."""
    files={'raw_supervisor_sha256':run/'gate.supervisor.json','worker_claim_sha256':run/'worker.claim',
        'ready_sha256':run/'gate.ready.json','go_sha256':run/'gate.go.json','result_sha256':run/'result.json','receipt_sha256':run/'receipt.json'}
    proof={k:sha(p) if p.exists() else None for k,p in files.items()}
    proof.update({k:ledger.get(k) for k in ['run_id','grant_sha256','nonce','binding_sha256']})
    proof.update({k:raw.get(k) for k in ['process_exit_confirmed','owned_launcher_exit_confirmed','go_issued','returncode']})
    proof.update(identity_verified=False,worker_pid=None,result_digest=None)
    if all(p.exists() for p in files.values()):
        claim=read(run/'worker.claim');ready=read(run/'gate.ready.json');go=read(run/'gate.go.json');result=read(run/'result.json')
        receipt=read(run/'receipt.json')
        pid=claim.get('pid');proof['worker_pid']=pid;proof['result_digest']=__import__('sac_scope').digest(result)
        proof['identity_verified']=bool(type(pid) is int and pid>0 and pid==ready.get('proof',{}).get('pid')==go.get('pid')==result.get('worker_pid') and
            claim.get('nonce')==ledger.get('nonce') and go.get('parent_pid')==ledger.get('owner_pid') and
            go.get('registered_at')==ready.get('registered_at') and go.get('job_assigned') is True and
            all(result.get(k)==ledger.get(k)==receipt.get(k) for k in ['run_id','grant_sha256','nonce','binding_sha256']) and
            receipt.get('worker_pid')==pid and receipt.get('status')=='finished' and
            all(type(receipt.get(k)) is int and receipt[k]==v for k,v in dict(tensor_load_attempts=2,tensor_loads=2,
                actor_construction_attempts=2,actor_constructions=2,reference_learner_construction_attempts=2,reference_learner_constructions=2,
                policy_call_attempts=64,policy_calls=64,formal_updates=0,optimizer_steps=0,replay_publications=0,native_steps=0).items()))
    return proof

def execute(args):
    g,binding,cfg=checked_grant(args)
    if os.name!='nt':raise OSError('Qualified Windows process-tree supervision required')
    execution=directory(args.kind);execution.mkdir(exist_ok=False);nonce=uuid.uuid4().hex
    ledger=dict(kind=args.kind,status='RESERVED',run_id=args.run_id,grant_path=str(Path(args.grant).resolve()),
        grant_sha256=args.grant_pin,binding_sha256=sha(OUT/'source_binding.json'),matrix_scope_key=cfg['common_key'],
        cumulative_before=279,episodes=[],limits=limits(args.kind),started_at=now(),nonce=nonce,owner_pid=os.getpid())
    write(execution/'ledger.json',ledger);write(execution/'launch.json',dict(run_id=args.run_id,nonce=nonce,grant_sha256=args.grant_pin))
    gate=execution/('gate' if args.kind=='numeric' else 'package_gate')
    try:helper('supervised').bounded_process(command(binding,args,'worker' if args.kind=='numeric' else 'coordinator',nonce),gate,limits(args.kind)['whole_wall_s'])
    finally:
        ledger=read(execution/'ledger.json');supervisor=Path(str(gate)+'.supervisor.json');proof=read(supervisor) if supervisor.exists() else {}
        ledger['package_supervisor']=proof
        if args.kind=='physical':reconcile(ledger,execution,proof)
        elif (execution/'receipt.json').exists():ledger['receipt']=read(execution/'receipt.json');ledger['receipt_sha256']=sha(execution/'receipt.json')
        if ledger['status'] not in ('CLOSED_COMPLETE','CLOSED_EARLY','CLOSED_ERROR') or not (
            proof.get('process_exit_confirmed') is True and proof.get('owned_launcher_exit_confirmed') is True and proof.get('returncode')==0):
            ledger.update(status='CLOSED_ERROR',error='Package exit or worker close not confirmed')
        if args.kind=='numeric':
            write(execution/'numeric_exit_proof.json',numeric_exit_proof(execution,ledger,proof))
            ledger['numeric_exit_proof_sha256']=sha(execution/'numeric_exit_proof.json')
        close(execution,ledger)

def main():
    parser=argparse.ArgumentParser();group=parser.add_mutually_exclusive_group(required=True)
    for name in ['check','execute','worker','coordinator']:group.add_argument('--'+name,action='store_true')
    parser.add_argument('--kind',choices=['numeric','physical'])
    for name in ['grant','grant-pin','run-id','nonce']:parser.add_argument('--'+name)
    parser.add_argument('--case-index',type=int)
    parser.add_argument('gate',nargs='?');parser.add_argument('parent_pid',nargs='?',type=int);parser.add_argument('registered_at',nargs='?',type=float)
    args=parser.parse_args()
    if args.check:
        verify_binding();print(json.dumps(dict(bound_sources_verified=True,new_evaluations=42,numeric_equivalence_passed=False,scientific_execution_admitted=False,training_admitted=False)))
    elif args.worker:worker(args)
    elif args.coordinator:coordinator(args)
    else:execute(args)

if __name__=='__main__':main()

