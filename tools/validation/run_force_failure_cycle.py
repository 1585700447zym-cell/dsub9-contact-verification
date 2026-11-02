"""Single authorized cycle; controlled failure-frequency stop is not a crash."""
import argparse,ctypes,gzip,importlib.util,json,os,subprocess,sys,time
from pathlib import Path
from tools.learning.force_failure_cycle import (ROOT,DELIVERY,OLD,ForceAdmission,ForceLedger,
    accounting,verify_candidate,verify_initial_chain,reuse_baseline,read)
from tools.learning.admitted_collection import _write_json as write
from tools.learning.bounded_contact import ForceFailureStop
from tools.learning.episode_rules import FORCE_ONLY
from tools.learning.admission import digest

CONTROLLED_EXIT=20

def claim(name):
    with (DELIVERY/(name+'_claim.json')).open('x',encoding='utf-8') as f:
        json.dump(dict(pid=os.getpid(),parent_pid=os.getppid(),wall_timestamp=time.time()),f)

def child_command(candidate_pin,authorization_pin,*,restore=False):
    return [sys.executable,'-X','utf8','-X','faulthandler','-B','-m','tools.validation.run_force_failure_cycle',
        '--candidate-sha256',candidate_pin,'--authorization-sha256',authorization_pin,
        '--restore' if restore else '--worker']

def require_parent(restore):
    from tools.validation.process_parent import require_registered_parent
    record=read(DELIVERY/('worker_claim.json' if restore else 'started.json'))
    return require_registered_parent(record['pid' if restore else 'supervisor_pid'],record['wall_timestamp'])

def checkpoint_integrity(path,expected_digest=None):
    pin=digest(path/'manifest.json');manifest=read(path/'manifest.json')
    if ((expected_digest is not None and pin!=expected_digest)
            or manifest['version']!='bounded_checkpoint_manifest_v2'
            or digest(path/'state.pt')!=manifest['state_sha256']):
        raise ValueError('Checkpoint manifest or payload changed')
    return pin


def stage_integrity(run,stage,rows,qualification,checkpoint_pin):
    """Verify durable originals and their identities; full physics audit stays separate."""
    from tools.learning.bounded_cycle import cases
    from tools.learning.bounded_contact import case_at,POINTS,SEED
    training=stage=='training'
    points=[case_at(f'train_{i:02d}',*POINTS[i%4]) for i in range(12)] if training else cases(stage.startswith('holdout'))
    names=[c['name'] for c in points]
    receipts=read(run/stage/'attempts.json')
    if ([r['id'] for r in rows]!=names or [r['episode_id'] for r in receipts]!=names):
        raise ValueError('Missing or unregistered stage attempts')
    results=[r['result'] for r in rows]
    if not training and read(run/stage/'results.json')!=results:
        raise ValueError('Evaluation results differ from finished ledger')
    archives={}
    for case,row,receipt in zip(points,results,receipts):
        folder=run/'training_episodes'/case['name'] if training else run/stage/'episodes'/case['name']
        path=folder/'episode.json.gz'
        if read(folder/'status.json')!=receipt or digest(path)!=receipt['archive_sha256']:
            raise ValueError('Episode original or receipt changed')
        raw=json.loads(gzip.decompress(path.read_bytes()));outcome=raw['outcome'];n=len(raw['transitions'])
        if (raw.get('fault') is not None or not 0<n<=13000 or receipt['steps']!=n or row['cycles']!=n
                or any(raw[k]!=receipt[k] for k in ('episode_id','case','seed','qualification_sha256','guard_clear','learning_eligibility'))
                or raw['episode_id']!=case['name'] or raw['case']!=case or raw['seed']!=SEED
                or raw['qualification_sha256']!=qualification or not FORCE_ONLY.receipt_valid(receipt)
                or receipt['status']!=('published' if training else 'evaluation_archived')
                or receipt['committed']!=(n if training else 0) or receipt['discarded']!=(0 if training else n)
                or any(outcome[k] is not True or receipt[k] is not True for k in ('simulation_valid','physical_stopped','valid_for_learning'))
                or row['simulation_valid'] is not True or row['physical_stopped'] is not True
                or not outcome['task_outcome']==receipt['task_outcome']==row['task_outcome']
                or row['success'] is not (outcome['task_outcome']=='FULL_SUCCESS')):
            raise ValueError('Episode identity, outcome or publication differs')
        if not training:
            method='zero_b2' if stage=='holdout_b2' else 'sac'
            if (row['case']!=case['name'] or any(r['training_admitted'] is not False
                    or r['evaluation_method']!=method or r['checkpoint_sha256']!=checkpoint_pin for r in (raw,receipt))
                    or (method=='zero_b2' and raw['guard_clear'] is not True)):
                raise ValueError('Evaluation point or selected checkpoint differs')
        archives[path.relative_to(ROOT).as_posix()]=receipt['archive_sha256']
    if training and FORCE_ONLY.stop_reason(receipts):raise ValueError('Training crossed a force-frequency stop')
    return archives


def completion_ready(run):
    from tools.learning.bounded_cycle import validate_holdout_evidence
    s=read(run/'ledger.json');a=accounting(s)
    if (s['status']!='healthy' or s['active'] is not None or a['new_dynamic_starts']!=32
            or (run/'failure.json').exists() or (run/'controlled_stop.json').exists()):
        raise ValueError('Full healthy stage ledger required')
    if [r['stage'] for r in s['attempts']]!=[stage for stage,n in ForceLedger.CAPS.items() for _ in range(n)]:
        raise ValueError('Stage order differs')
    for stage,n in ForceLedger.CAPS.items():
        rows=[r for r in s['attempts'] if r['stage']==stage]
        if len(rows)!=n or any(r['status']!='finished' for r in rows):raise ValueError('Incomplete stage')
    frozen=read(run/'frozen.json');budget=read(run/'training_episodes/update_budget.json')
    if frozen['episodes']!=12 or frozen['updates']!=4500 or budget['attempted']!=4500 or budget['completed']!=4500:
        raise ValueError('Missing fixed final checkpoint or update accounting')
    checkpoints=read(run/'training/checkpoints.json')
    if len(checkpoints)!=12 or checkpoints[-1]!=frozen:raise ValueError('Fixed episode 12 checkpoint missing')
    for i,entry in enumerate(checkpoints):
        if (entry['path']!=f'training/checkpoints/train_{i:02d}' or entry['episodes']!=i+1
                or entry['updates']!=max(0,i-2)*500):raise ValueError('Checkpoint boundary differs')
        checkpoint_integrity(run/entry['path'],entry['sha256'])
    initial_pin=checkpoint_integrity(run/'initial_checkpoint');qualification=digest(run.parent/'candidate.json')
    stage_archives={}
    for stage in ForceLedger.CAPS:
        rows=[r for r in s['attempts'] if r['stage']==stage]
        stage_archives[stage]=stage_integrity(run,stage,rows,qualification,initial_pin if stage=='initial' else frozen['sha256'])
    for stage in ('initial','final','restored','holdout_b2','holdout_sac'):
        if read(run/stage/'verification.json')['training_state_unchanged'] is not True:
            raise ValueError('Evaluation changed learning state')
    restoration=read(run/'restoration.json');gate=read(run/'holdout_scope_gate.json')
    child=read(run/'restore_process_exit.json')
    if (restoration['exact_physical_replay'] is not True or restoration['independent_performance_samples_added']!=0
            or child['role']!='restore' or child['returncode']!=0 or gate['passed'] is not True
            or gate['qualification_sha256']!=qualification or gate['frozen_checkpoint_sha256']!=digest(run/'frozen.json')
            or gate['archives']!=stage_archives['holdout_b2']):raise ValueError('Missing restoration/scope gate')
    validate_holdout_evidence(gate['evidence'])
    return a

def valid_controlled_stop(run):
    s=read(run/'ledger.json');r=read(run/'controlled_stop.json');accounting(s)
    rows=s['attempts'];training=[x for x in rows if x['stage']=='training']
    reason=FORCE_ONLY.stop_reason([x['result'] for x in training if x['status']=='finished'])
    return (s['status']=='stopped' and s['active'] is None and bool(rows) and bool(reason)
        and s.get('stop_kind')==r.get('kind')=='force_failure_frequency'
        and s.get('stop_reason')==r.get('reason')==reason
        and r.get('episode_id')==rows[-1]['id'] and rows[-1]['stage']=='training'
        and rows[-1]['status']=='finished' and rows[-1]['result']['task_outcome']=='CONTACT_GUARD'
        and not (run/'failure.json').exists() and not (run/'completed.json').exists())

def seal_failure(delivery,result,interrupted_status):
    run=Path(delivery)/'run';run.mkdir(parents=True,exist_ok=True)
    if (run/'failure.json').exists():result['underlying_failure']=read(run/'failure.json')
    if (run/'ledger.json').exists():
        state=read(run/'ledger.json');state.update(status='failed',error=result['kind'])
        if state['active'] is not None:
            state['attempts'][state['active']].update(status=interrupted_status,valid_for_learning=False)
        state['active']=None
        write(run/'ledger.json',state);write(run/'cumulative_budget.json',accounting(state))
    write(run/'failure.json',result)


def finalize_supervisor_error(exc,delivery):
    delivery=Path(delivery)
    receipt=read(delivery/'process_exit.json') if (delivery/'process_exit.json').exists() else {}
    confirmed=receipt.get('status')=='supervisor_error' and receipt.get('worker_stopped') is True and receipt.get('cleanup_error') is None
    result=dict(kind='supervisor_error',error=repr(exc),worker_stopped=confirmed,
        cleanup_error=receipt.get('cleanup_error') if confirmed else receipt.get('cleanup_error') or 'Cleanup not confirmed',
        process_exit=receipt,execution_complete=False,retry_allowed=False,b2_complete=False,wall_timestamp=time.time())
    seal_failure(delivery,result,'interrupted_by_supervisor_error')
    write(delivery/'run/notification.json',result);write(delivery/'exit_classification.json',result)
    return result


def finalize_exit(code,delivery):
    delivery=Path(delivery);run=delivery/'run';complete=False
    run.mkdir(parents=True,exist_ok=True)  # A rejected worker may never have created it.
    child=read(run/'restore_process_exit.json') if (run/'restore_process_exit.json').exists() else None
    if code & 0xC0000000 == 0xC0000000:kind='native_crash'
    elif child and child['returncode'] & 0xC0000000 == 0xC0000000:kind='native_crash'
    elif code==CONTROLLED_EXIT:
        try:valid=valid_controlled_stop(run)
        except (OSError,ValueError,KeyError,TypeError):valid=False
        kind='force_failure_frequency' if valid else 'invalid_controlled_stop'
    elif code==0:
        try:
            completion_ready(run)
            complete=read(run/'completed.json')['status']=='execution_complete'
        except (OSError,ValueError,KeyError,TypeError,EOFError):complete=False
        kind='execution_complete' if complete else 'incomplete_execution'
    else:kind='execution_failure' if (run/'ledger.json').exists() else 'entry_rejection'
    result=dict(kind=kind,execution_complete=complete,returncode=code,returncode_hex=hex(code & 0xffffffff),
        retry_allowed=False,b2_complete=False,wall_timestamp=time.time())
    if child is not None:result['child_process']=child
    if kind not in ('force_failure_frequency','execution_complete'):
        seal_failure(delivery,result,'interrupted_by_process_exit')
    write(run/'notification.json',result);write(delivery/'exit_classification.json',result)
    return result

def worker(permit,*,restore=False):
    require_parent(restore)
    if os.name=='nt':ctypes.windll.kernel32.SetErrorMode(0x0002)
    claim('restore' if restore else 'worker')
    from tools.learning import bounded_checkpoint as cp
    from tools.learning.bounded_contact import BoundedCollection
    from tools.learning.bounded_cycle import train,evaluate,cases,same_physical_result,holdout_scope_gate,compare_success,progress
    from tools.learning.repaired_cycle import development_decision
    run=DELIVERY/'run';chain=None;ledger=None
    try:
        if restore:
            frozen=read(run/'frozen.json')
            chain=cp.load_checkpoint(run/frozen['path'],expected_digest=frozen['sha256'],admission=permit,
                output=run/'restored_training_state')
            ledger=ForceLedger(run/'ledger.json')
            evaluate(chain,'restored',ledger=ledger,output=run/'restored',checkpoint_sha256=frozen['sha256'])
            for case in cases():
                a=json.loads(gzip.decompress((run/'final/episodes'/case['name']/'episode.json.gz').read_bytes()))
                b=json.loads(gzip.decompress((run/'restored/episodes'/case['name']/'episode.json.gz').read_bytes()))
                if not same_physical_result(a,b):raise RuntimeError('Restored physical trajectory differs')
            write(run/'restoration.json',dict(exact_physical_replay=True,independent_performance_samples_added=0));return
        run.mkdir(exist_ok=False);ledger=ForceLedger(run/'ledger.json')
        chain=BoundedCollection(admission=permit,output=run/'training_episodes')
        write(run/'initial_state_identity.json',verify_initial_chain(chain))
        initial_pin=cp.save_checkpoint(chain,run/'initial_checkpoint');reuse_baseline(run)
        evaluate(chain,'initial',ledger=ledger,output=run/'initial',checkpoint_sha256=initial_pin)
        frozen=train(chain,ledger=ledger,output=run/'training');write(run/'frozen.json',frozen)
        evaluate(chain,'final',ledger=ledger,output=run/'final',checkpoint_sha256=frozen['sha256'])
        decision=development_decision(run)
        write(run/'notification.json',dict(kind='development_evaluation_complete',result=decision,
            next='Continue registered restoration and independent evaluation without more training.'))
        print(json.dumps(dict(stage='development_decision',**decision)),flush=True)
        with (run/'restore_process.log').open('x',encoding='utf-8') as f:
            result=subprocess.run(child_command(permit.expected_digest,permit.authorization_digest,restore=True),
                cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
        ledger=ForceLedger(run/'ledger.json')
        write(run/'restore_process_exit.json',dict(role='restore',returncode=result.returncode,
            returncode_hex=hex(result.returncode & 0xffffffff),wall_timestamp=time.time()))
        if result.returncode:raise RuntimeError('Separate restoration process failed: '+str(result.returncode))
        evaluate(chain,'holdout_b2',ledger=ledger,output=run/'holdout_b2',checkpoint_sha256=frozen['sha256'])
        holdout_scope_gate(run,permit)
        evaluate(chain,'holdout_sac',ledger=ledger,output=run/'holdout_sac',checkpoint_sha256=frozen['sha256'])
        independent=compare_success(read(run/'holdout_b2/results.json'),read(run/'holdout_sac/results.json'))
        permit.verify();totals=completion_ready(run)
        write(run/'completed.json',dict(status='execution_complete',**totals,formal_updates=chain.updater.counts,
            independent=independent,checkpoint=frozen,b2_complete=False,offline_result_audit_pending=True))
        progress(run/'progress.json',stage='completed',independent=independent)
    except ForceFailureStop as exc:
        write(run/'controlled_stop.json',dict(**exc.record(),ledger=ledger.state))
        progress(run/'progress.json',stage='stopped',**exc.record())
        raise
    except BaseException as exc:
        if chain is not None:chain.fail(exc)
        if ledger is not None:ledger.fail(repr(exc))
        failure=dict(error=repr(exc))
        if (run/'failure.json').exists():failure['previous_failure']=read(run/'failure.json')
        write(run/'failure.json',failure)
        progress(run/'progress.json',stage='failed',error=repr(exc));raise
    finally:
        if ledger is not None:write(run/'cumulative_budget.json',accounting(ledger.state))

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--candidate-sha256',required=True)
    p.add_argument('--authorization-sha256');modes=p.add_mutually_exclusive_group()
    for name in ('worker','restore','verify-only'):modes.add_argument('--'+name,action='store_true')
    args=p.parse_args(argv)
    if args.verify_only:
        verify_candidate(DELIVERY/'candidate.json',args.candidate_sha256)
        print('Technical qualification verified; execution still requires a separate authorization pin.');return 0
    permit=ForceAdmission(DELIVERY/'candidate.json',expected_digest=args.candidate_sha256,
        authorization_digest=args.authorization_sha256)
    if args.worker or args.restore:
        try:worker(permit,restore=args.restore)
        except ForceFailureStop:return CONTROLLED_EXIT
        return 0
    source=OLD/'retry_01/driver.py'
    spec=importlib.util.spec_from_file_location('frozen_retry_supervisor',source)
    supervisor=importlib.util.module_from_spec(spec);spec.loader.exec_module(supervisor)
    try:code=supervisor.supervise(child_command(args.candidate_sha256,args.authorization_sha256),DELIVERY,ROOT)
    except FileExistsError:raise  # Never label an existing live launch as failed.
    except BaseException as exc:
        finalize_supervisor_error(exc,DELIVERY)
        raise
    result=finalize_exit(code,DELIVERY)
    return 0 if result['execution_complete'] else (CONTROLLED_EXIT if result['kind']=='force_failure_frequency' else 1)

if __name__=='__main__':raise SystemExit(main())
