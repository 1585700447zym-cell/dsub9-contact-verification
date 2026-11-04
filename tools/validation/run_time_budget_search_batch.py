"""Eight paired 450/900 zero-update runs under the new time-only protocol."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from copy import deepcopy
from dataclasses import asdict
import json,math,os,sys,time,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.validation.run_yaw_pilot import read,sha,write,publish_archive,actual_common,model_archive_bytes,supervise
from tools.learning.noise50_trial import VERSION as NOISE_VERSION,behavior_contract
from tools.learning.time_budget_trial import VERSION,protocol_config
OUT=ROOT/'deliverables/learning_chain/time_budget_search_batch1_20261103'
PREVIOUS=ROOT/'deliverables/learning_chain/noise50_yaw_repeat_20261103'
MODIFICATION=ROOT/'deliverables/learning_chain/time_budget_search_20261103'
BATCH_VERSION='time_budget_search_450_900_batch1_v1'
CUMULATIVE_BEFORE=447
PARENT=ROOT/'deliverables/learning_chain/consistent_reference_sac_20261029'
PYTHON=ROOT/'tmp/learning_cpu_20260924/Scripts/python.exe'
COMMON=('dynamic_config','effective_kd','model_xml_sha256','actual_model','runtime')
MAX_CYCLES=16000


def canonical(v): return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False)

def schedule():
    from tools.validation.run_noise50_yaw_repeat import schedule as prior_schedule
    result=[]
    for old in prior_schedule():
        for speed in (450,900):
            job=deepcopy(old)
            job.update(id=f'S{speed}_{old["id"]}',search_speed_um_s=speed,
                       purpose='new_time_budget_search_speed_pair')
            result.append(job)
    return result


def validate_schedule(jobs):
    if jobs!=schedule():
        raise ValueError('Exactly four matched 450/900 pairs, yaw ON and zero learning, required')


def verify_inputs(pins):
    for rel,h in pins.items():
        if sha(ROOT/rel)!=h: raise ValueError('Frozen input changed: '+rel)


def current_referee():
    from tools.model.layered_task import TASK_ID,referee_metadata,GEOMETRY_TOLERANCE_M
    if TASK_ID!='dsub9_clearance120_layered_nano10_v5' or GEOMETRY_TOLERANCE_M!=1e-8:
        raise ValueError('Authorized current nano10/v5 referee required')
    return TASK_ID,referee_metadata()


def verify_active_yaw(raw):
    from tools.learning.noise50_trial import verify_passive_channel
    proof=verify_passive_channel(raw,True)
    if proof['recurrence_updates_checked']<=0:
        raise ValueError('Passive yaw ON requires actual feedback update evidence')
    return proof


def prepare():
    if (OUT/'registration.json').exists(): raise FileExistsError('Existing batch is never replaced')
    prior=read(PARENT/'registration.json');close=read(PARENT/'completion_verification.json');frozen=read(PARENT/'frozen_policy.json')
    previous=read(PREVIOUS/'summary.json');previous_close=read(PREVIOUS/'completion_verification.json')
    prevreg=read(PREVIOUS/'registration.json');qualified=read(MODIFICATION/'verification.json')
    if (not close['verified'] or frozen['updates']!=4000 or previous['cumulative_initializations']!=447
            or previous['completed_episodes']!=4 or previous['status']!='COMPLETED' or not previous_close['verified']
            or not qualified['verified'] or qualified['pure_checks_passed']!=176 or qualified['cumulative_initializations']!=447):
        raise ValueError('Closed F4000, cumulative447 and qualified new protocol required')
    verify_inputs(qualified['source_sha256']);verify_inputs(qualified['protected_working_sources'])
    expected=set(qualified['source_sha256']) & set(prevreg['inputs'])
    changed={name for name,h in prevreg['inputs'].items() if sha(ROOT/name)!=h}
    if changed!=expected:raise ValueError('Changes outside qualified implementation: '+repr(changed ^ expected))
    from tools.validation.run_consistent_sac import select
    select(prior)
    task,referee=current_referee()
    paths=[ROOT/p for p in prevreg['inputs']]+[ROOT/p for p in qualified['source_sha256']]+[ROOT/p for p in (
        'tools/validation/run_time_budget_search_batch.py','tests/test_time_budget_search_batch.py',
        'docs/superpowers/plans/2026-11-03-time-budget-first-batch.md',
        'deliverables/learning_chain/time_budget_search_20261103/verification.json',
        'deliverables/learning_chain/time_budget_search_20261103/review.json')]
    OUT.mkdir();pins={}
    for path in sorted(set(paths)):
        rel=path.relative_to(ROOT).as_posix();target=OUT/'source_snapshot'/rel
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(path.read_bytes());pins[rel]=sha(path)
    contracts={str(v):protocol_config(v) for v in (450,900)}
    reg=dict(version=BATCH_VERSION,protocol_version=VERSION,behavior_version=NOISE_VERSION,task_id=task,geometry_referee=referee,
        inputs=pins,config=prior['config'],execution_contracts=contracts,common=prevreg['common'],
        schedule=schedule(),source_checkpoint=frozen['checkpoint'],source_checkpoint_sha256=frozen['checkpoint_sha256'],source_policy_sha256=frozen['policy_sha256'],
        source_frozen_record_sha256=sha(PARENT/'frozen_policy.json'),source_closeout_sha256=sha(PARENT/'completion_verification.json'),runtime_sha256=prior['runtime_sha256'],
        previous_summary_sha256=sha(PREVIOUS/'summary.json'),previous_closeout_sha256=sha(PREVIOUS/'completion_verification.json'),
        modification_verification_sha256=sha(MODIFICATION/'verification.json'),
        max_initializations=8,max_physical_substeps=1280000,total_updates=0,cumulative_before=CUMULATIVE_BEFORE,max_worker_wall_s=1800,max_batch_wall_s=10800,
        max_parallel_workers=2,retries=0,final_test_episodes=0,noise_hold_cycles=25,
        source_changes_from_previous=sorted(changed),
        comparison='New450 vs new900 on identical time-only retry and warning-only risk protocol; matched original four development conditions; frozen F4000',
        authorization='2026-11-03 user requested the first actual batch under the modified plan; eight paired runs, zero updates, no fixed-zero controls')
    validate_schedule(reg['schedule'])
    write(OUT/'registration.json',reg)
    write(OUT/'preparation.json',dict(verified=True,registration_sha256=sha(OUT/'registration.json'),new_initializations=0,new_physical_substeps=0,new_neural_inference=0,new_optimizer_updates=0))
    print(json.dumps(dict(prepared=True,initializations=8,updates=0,frozen_inputs=len(pins),task_id=task)))


def ready():
    reg=read(OUT/'registration.json');prep=read(OUT/'preparation.json')
    validate_schedule(reg['schedule'])
    if (reg['version']!=BATCH_VERSION or reg['protocol_version']!=VERSION or reg['total_updates']!=0 or reg['cumulative_before']!=447
            or reg['max_initializations']!=8 or reg['max_physical_substeps']!=1280000
            or reg['execution_contracts']!={str(v):protocol_config(v) for v in (450,900)}
            or reg['noise_hold_cycles']!=25 or reg['retries']!=0 or reg['final_test_episodes']!=0
            or prep['registration_sha256']!=sha(OUT/'registration.json')):
        raise ValueError('Frozen schedule/budget/registration changed')
    verify_inputs(reg['inputs'])
    from tools.validation.run_consistent_sac import select
    select(reg)
    task,referee=current_referee()
    if reg['task_id']!=task or reg['geometry_referee']!=referee:raise ValueError('Current registered referee differs')
    for path,key in ((PARENT/'frozen_policy.json','source_frozen_record_sha256'),
                     (PARENT/'completion_verification.json','source_closeout_sha256'),
                     (PREVIOUS/'summary.json','previous_summary_sha256'),
                     (PREVIOUS/'completion_verification.json','previous_closeout_sha256'),
                     (MODIFICATION/'verification.json','modification_verification_sha256')):
        if sha(path)!=reg[key]:raise ValueError('Original source record changed: '+str(path))
    return reg


def worker(job_id):
    reg=ready();job=next(j for j in reg['schedule'] if j['id']==job_id);folder=OUT/'run'/job_id
    with (folder/'worker.claim').open('x') as f:f.write(str(os.getpid()))
    start=time.monotonic();env=session=trainer=provider=source_provider=raw=None
    contract=reg['execution_contracts'][str(job['search_speed_um_s'])]
    job_reg=dict(reg,execution_contract=contract)
    receipt=dict(case_id=job_id,stage='online',purpose=job['purpose'],behavior_contract=behavior_contract(job['passive_yaw_enabled']),
        execution_contract=contract,search_speed_um_s=job['search_speed_um_s'],task_id=reg['task_id'],geometry_referee=reg['geometry_referee'],case=job['case'],seed=job['seed'],noise_seed=job['noise_seed'],
        registration_sha256=sha(OUT/'registration.json'),reset_attempted=0,reset_completed=0,physical_substeps=0,control_cycles=0,
        status='initializing',valid=False,stopped=False,policy_calls=0,warmup_draws=0,training_updates=0)
    result=dict(status='LOADING',actual_updates_for_job=0,attempted_updates_for_job=0)
    write(folder/'receipt.json',receipt);write(folder/'job_result.json',result)
    def enforce():
        if time.monotonic()-start>reg['max_worker_wall_s'] or (OUT/'STOP').exists():raise RuntimeError('Diagnostic runtime/stop bound; no retry')
    try:
        from tools.validation.run_consistent_sac import select,policy_digest,audit_source_copy
        runtime=select(reg)
        from tools.learning.consistent_sac import load_checkpoint,CollectionError
        from tools.learning.time_budget_trial import environment_class,session_class,collect_episode,audit_archive
        from tools.learning.noise50_trial import FrozenHeldPolicy,HeldSourceReplay,source_contexts,verify_passive_channel
        from tools.learning.newton_profile import build_model_xml
        from tools.validation.yaw_pilot import YawContactCase
        trainer=load_checkpoint(reg['source_checkpoint'],expected_digest=reg['source_checkpoint_sha256'],config=reg['config'])
        counts_before=deepcopy(trainer.updater.counts);attempts_before=trainer.update_attempts;replay_before=len(trainer.replay)
        if any(v!=4000 for v in counts_before.values()) or policy_digest(trainer)!=reg['source_policy_sha256']:raise ValueError('Exact frozen F4000 source required')
        source_trainer=audit_source_copy(trainer)
        provider=FrozenHeldPolicy(trainer,job['noise_seed']);source_provider=FrozenHeldPolicy(source_trainer,job['noise_seed'])
        receipt.update(source_checkpoint_sha256=reg['source_checkpoint_sha256'],source_policy_sha256=reg['source_policy_sha256'])
        env=environment_class()();model=model_archive_bytes(build_model_xml(env.profile));(folder/'model_used.xml').write_bytes(model)
        receipt.update(actual_common(env,runtime,model))
        if any(canonical(receipt[k])!=canonical(reg['common'][k]) for k in COMMON):raise ValueError('Common native domain differs')
        Base=session_class(job['search_speed_um_s'])
        class Bounded(Base):
            def advance_cycle(self,action):
                enforce();before=self.prepare_cycle();cycle=self.cycle_id
                if not before.residual_enabled:
                    provider.select(None,cycle=cycle,phase=before.controller_state['phase'],enabled=False)
                if provider.sampler.clock_last_cycle!=cycle or not (provider.last_action==action).all():raise ValueError('Same-cycle held source differs')
                source_log=deepcopy(provider.last_log)
                value=super().advance_cycle(action)
                value.action_log['noise50']=source_log
                provider.finish_cycle(value.next_snapshot.residual_enabled)
                if self.cycle_id%100==0:
                    write(folder/'progress.json',dict(cycles=self.cycle_id,simulation_s=self.cycle_id*.002,physical_substeps=env.physical_steps,
                        reset_attempted=1,policy_calls=provider.policy_calls,warmup_draws=0,training_updates=0,noise_refreshes=provider.sampler.clock_draw_count,
                        phase=value.next_snapshot.controller_state['phase']))
                return value
        session=Bounded(env);point=YawContactCase(**job['case']);receipt['reset_attempted']=1;write(folder/'receipt.json',receipt)
        result['status']='COLLECTING';write(folder/'job_result.json',result)
        def choose(obs):
            before=session.prepare_cycle()
            return provider.select(obs,cycle=session.cycle_id,phase=before.controller_state['phase'],enabled=True)
        try:raw=collect_episode(session,point,policy=choose,seed=job['seed'],max_cycles=MAX_CYCLES)
        except CollectionError as exc:raw=exc.archive;raise
        finally:
            if raw is not None:
                raw.update(policy_calls=provider.policy_calls,warmup_draws=0,behavior_contract=receipt['behavior_contract'],noise_seed=job['noise_seed'],task_id=reg['task_id'],geometry_referee=reg['geometry_referee'])
                receipt.update(physical_substeps=env.physical_steps,control_cycles=session.cycle_id,guard_facts=env.guard_facts,
                    reference_checks=env.reference_checks,reference_corrections=env.reference_envelope_corrections,
                    reset_completed=raw['cost']['initializations_completed'],policy_calls=provider.policy_calls)
                if raw.get('outcome'):
                    receipt.update(status='error' if raw.get('error') else 'finished',valid=raw['outcome']['simulation_valid'],stopped=raw['outcome']['physical_stopped'],
                        outcome=raw['outcome']['task_outcome'],final_reason=session.reason,finish_criteria=session.finish_criteria,
                        initialization_guard_config=asdict(env.guard_config),controller_config=asdict(session.controller.config),controller_metadata=session.controller.metadata(),
                        task_time_s=session.task_end_time,stop_time_s=session.stop_time,audit_end_time_s=float(env.data.time))
                receipt['elapsed_wall_s']=time.monotonic()-start
                publish_archive(folder,raw,receipt)
        contexts=source_contexts(raw);actual_sampler=provider.sampler.state_dict();raw=None
        result['status']='AUDITING';write(folder/'job_result.json',result)
        adapter=HeldSourceReplay(source_provider,contexts)
        audited,receipt,proof=audit_archive(folder,job_reg,job,search_speed_um_s=job['search_speed_um_s'],source_trainer=adapter)
        result['audit_neural_policy_calls']=adapter.policy_calls
        if canonical(adapter.finish())!=canonical(actual_sampler):raise ValueError('Held source endpoint differs')
        if (audited.get('behavior_contract')!=behavior_contract(job['passive_yaw_enabled']) or audited.get('noise_seed')!=job['noise_seed']):raise ValueError('Behavior contract differs')
        proof.update(task_id=reg['task_id'],geometry_referee=reg['geometry_referee'],behavior_version=NOISE_VERSION,protocol_version=VERSION,noise_source_replay_verified=True,noise_refreshes=provider.sampler.clock_draw_count,
            passive_channel=verify_active_yaw(audited),optimizer_updates=0,replay_publication=False)
        if (trainer.updater.counts!=counts_before or trainer.update_attempts!=attempts_before or len(trainer.replay)!=replay_before or policy_digest(trainer)!=reg['source_policy_sha256']):raise ValueError('Frozen learning state changed')
        write(folder/'sampler_final.json',actual_sampler);write(folder/'audit.json',proof)
        result.update(status='FINISHED',outcome=receipt['outcome'],final_reason=receipt['final_reason'],policy_calls=provider.policy_calls,
            noise_refreshes=provider.sampler.clock_draw_count,updater_counts=trainer.updater.counts,source_policy_sha256=reg['source_policy_sha256'],elapsed_wall_s=time.monotonic()-start)
        write(folder/'job_result.json',result)
    except BaseException as exc:
        result.update(status='FAILED',error=repr(exc),elapsed_wall_s=time.monotonic()-start)
        if provider is not None: result['policy_calls']=provider.policy_calls
        if source_provider is not None: result['audit_neural_policy_calls']=source_provider.policy_calls
        write(folder/'job_result.json',result);raise
    finally:
        if env is not None and hasattr(env,'model'):
            pass  # No additional physics, reset, or recovery during cleanup.


def summarize(reg):
    rows=[]
    for job in reg['schedule']:
        folder=OUT/'run'/job['id']
        if not folder.exists():continue
        r=read(folder/'receipt.json') if (folder/'receipt.json').exists() else {};p=read(folder/'progress.json') if (folder/'progress.json').exists() else {}
        j=read(folder/'job_result.json') if (folder/'job_result.json').exists() else {};s=read(folder/'supervisor.json') if (folder/'supervisor.json').exists() else {}
        rows.append(dict(id=job['id'],search_speed_um_s=job['search_speed_um_s'],case=job['case']['name'],noise_seed=job['noise_seed'],complete=j.get('status')=='FINISHED' and s.get('process_exit_confirmed') is True and s.get('returncode')==0,
            initializations=max(r.get('reset_attempted',0),p.get('reset_attempted',0)),physical_substeps=max(r.get('physical_substeps',0),p.get('physical_substeps',0)),
            cycles=max(r.get('control_cycles',0),p.get('cycles',0)),policy_calls=max(r.get('policy_calls',0),p.get('policy_calls',0)),
            audit_neural_policy_calls=j.get('audit_neural_policy_calls',0),outcome=r.get('outcome'),reason=r.get('final_reason')))
    return dict(episodes=rows,initialization_attempts=sum(r['initializations'] for r in rows),physical_substeps=sum(r['physical_substeps'] for r in rows),
        policy_calls=sum(r['policy_calls'] for r in rows),audit_neural_policy_calls=sum(r['audit_neural_policy_calls'] for r in rows),training_updates=0,
        completed_episodes=sum(r['complete'] for r in rows),counts_exact=len(rows)==len(reg['schedule']) and all(r['complete'] for r in rows),cumulative_initializations=CUMULATIVE_BEFORE+sum(r['initializations'] for r in rows))


def run_pair(pair,launch):
    failed=None
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending={pool.submit(launch,job):job for job in pair}
        for future in as_completed(pending):
            job=pending[future]
            try:
                proof=future.result()
                result=read(OUT/'run'/job['id']/'job_result.json')
                ok=proof.get('returncode')==0 and proof.get('process_exit_confirmed') and result.get('status')=='FINISHED'
            except BaseException as exc:
                ok=False;proof=dict(error=repr(exc))
            if not ok and failed is None:
                failed=job['id']
                write(OUT/'STOP',dict(reason='unqualified_worker',case_id=failed,supervisor=proof))
    if failed is not None:
        raise RuntimeError('Unqualified diagnostic; no retry: '+failed)


def run():
    reg=ready();(OUT/'run').mkdir();write(OUT/'batch_started.json',dict(unix_s=time.time()));start=time.monotonic();status='RUNNING';error=None
    def ledger():
        v=summarize(reg);v.update(status=status,error=error,elapsed_wall_s=time.monotonic()-start);write(OUT/'ledger.json',v);return v
    def launch(job):
        ready();folder=OUT/'run'/job['id'];folder.mkdir()
        return supervise([str(PYTHON),'-B','-X','utf8',str(Path(__file__).resolve()),'--worker',job['id']],folder,timeout=reg['max_worker_wall_s']+180)
    ledger()
    try:
        for offset in range(0,len(reg['schedule']),2):
            if time.monotonic()-start>reg['max_batch_wall_s']:raise RuntimeError('Batch time bound')
            pair=reg['schedule'][offset:offset+2]
            run_pair(pair,launch)
            ledger()
            print(json.dumps(dict(pair=offset//2+1,completed=True,updates=0)),flush=True)
        status='COMPLETED'
    except BaseException as exc:status='STOPPED';error=repr(exc);raise
    finally:write(OUT/'summary.json',ledger())


def main():
    parser=argparse.ArgumentParser(description=__doc__);g=parser.add_mutually_exclusive_group(required=True)
    g.add_argument('--prepare',action='store_true');g.add_argument('--run',action='store_true');g.add_argument('--launch',action='store_true');g.add_argument('--worker')
    args=parser.parse_args()
    if args.prepare:prepare()
    elif args.worker:worker(args.worker)
    elif args.run:run()
    else:
        ready()
        with (OUT/'launcher.claim').open('x'):pass
        proof=dict(started=False,process_exit_confirmed=False,returncode=None)
        try:
            with (OUT/'launcher.log').open('xb') as log:
                proc=subprocess.Popen([str(PYTHON),'-B','-X','utf8',str(Path(__file__).resolve()),'--run'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                proof.update(started=True,pid=proc.pid,supervisor_pid=os.getpid());write(OUT/'process_started.json',proof)
                try:proof['returncode']=proc.wait()
                finally:proof['process_exit_confirmed']=proc.poll() is not None
        finally:write(OUT/'process_exit.json',proof)
        return proof['returncode']
    return 0

if __name__=='__main__':raise SystemExit(main())
