"""Four bounded zero-update held-noise / passive-yaw diagnostic episodes."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import asdict
import json,math,os,sys,time,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.validation.run_yaw_pilot import read,sha,write,publish_archive,actual_common,model_archive_bytes,supervise
from tools.learning.noise50_trial import VERSION,behavior_contract
OUT=ROOT/'deliverables/learning_chain/noise50_passive_yaw_20261030'
PARENT=ROOT/'deliverables/learning_chain/consistent_reference_sac_20261029'
PYTHON=ROOT/'tmp/learning_cpu_20260924/Scripts/python.exe'
COMMON=('dynamic_config','effective_kd','model_xml_sha256','actual_model','runtime')
MAX_CYCLES=16000


def canonical(v): return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False)

def schedule():
    result=[]
    for index,(name,angle) in enumerate((('P15',1.5),('M15',-1.5))):
        case=dict(name='YAW_'+name,x_offset_m=.0003,y_offset_m=.0003,roll_rad=math.radians(-1),pitch_rad=math.radians(1),yaw_rad=math.radians(angle),start_origin_z_m=-.005,target_depth_m=.005)
        for enabled in (True,False):
            result.append(dict(id=name+('_ON' if enabled else '_OFF'),stage='online',
                purpose='zero_update_passive_yaw_diagnostic',case=case,seed=2026092718+index,
                noise_seed=2026103001+index,passive_yaw_enabled=enabled,publish=False,updates_after=0))
    return result


def verify_inputs(pins):
    for rel,h in pins.items():
        if sha(ROOT/rel)!=h: raise ValueError('Frozen input changed: '+rel)


def prepare():
    if (OUT/'registration.json').exists(): raise FileExistsError('Existing diagnostic is never replaced')
    prior=read(PARENT/'registration.json');close=read(PARENT/'completion_verification.json');frozen=read(PARENT/'frozen_policy.json')
    if not close['verified'] or close['costs']['cumulative_initializations']!=439 or frozen['updates']!=4000: raise ValueError('Closed cumulative439/F4000 source required')
    verify_inputs(prior['inputs'])
    paths=[ROOT/p for p in prior['inputs']]+[ROOT/p for p in (
        'tools/learning/persistent_exploration.py','tools/learning/noise50_trial.py','tools/validation/run_noise50_yaw.py',
        'tests/test_persistent_exploration.py','tests/test_noise50_passive_yaw.py',
        'docs/superpowers/specs/2026-10-30-noise50-passive-yaw-design.md','docs/superpowers/plans/2026-10-30-noise50-passive-yaw.md')]
    OUT.mkdir(exist_ok=True);pins={}
    for path in sorted(set(paths)):
        rel=path.relative_to(ROOT).as_posix();target=OUT/'source_snapshot'/rel
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(path.read_bytes());pins[rel]=sha(path)
    reg=dict(version=VERSION,inputs=pins,config=prior['config'],execution_contract=prior['execution_contract'],common=prior['common'],
        schedule=schedule(),source_checkpoint=frozen['checkpoint'],source_checkpoint_sha256=frozen['checkpoint_sha256'],source_policy_sha256=frozen['policy_sha256'],
        source_frozen_record_sha256=sha(PARENT/'frozen_policy.json'),source_closeout_sha256=sha(PARENT/'completion_verification.json'),runtime_sha256=prior['runtime_sha256'],
        max_initializations=4,max_physical_substeps=640000,total_updates=0,cumulative_before=439,max_worker_wall_s=1800,max_batch_wall_s=5400,
        max_parallel_workers=2,retries=0,final_test_episodes=0,noise_hold_cycles=25,
        comparison='Same F4000/absolute-cycle epsilon; passive Mz-yaw channel ON/OFF at initial yaw +/-1.5deg; closed-loop diagnostic only',
        authorization='User requested 50ms exploration persistence and minimal passive-yaw influence comparison; no training, history or anchor change')
    write(OUT/'registration.json',reg)
    print(json.dumps(dict(prepared=True,initializations=4,updates=0,frozen_inputs=len(pins))))


def ready():
    reg=read(OUT/'registration.json')
    if reg['schedule']!=schedule() or reg['total_updates']!=0 or reg['cumulative_before']!=439: raise ValueError('Frozen schedule/budget changed')
    verify_inputs(reg['inputs'])
    if sha(PARENT/'frozen_policy.json')!=reg['source_frozen_record_sha256'] or sha(PARENT/'completion_verification.json')!=reg['source_closeout_sha256']:raise ValueError('Original source record changed')
    return reg


def worker(job_id):
    reg=ready();job=next(j for j in reg['schedule'] if j['id']==job_id);folder=OUT/'run'/job_id
    with (folder/'worker.claim').open('x') as f:f.write(str(os.getpid()))
    start=time.monotonic();env=session=trainer=provider=source_provider=raw=None
    receipt=dict(case_id=job_id,stage='online',purpose=job['purpose'],behavior_contract=behavior_contract(job['passive_yaw_enabled']),
        execution_contract=reg['execution_contract'],case=job['case'],seed=job['seed'],noise_seed=job['noise_seed'],
        registration_sha256=sha(OUT/'registration.json'),reset_attempted=0,reset_completed=0,physical_substeps=0,control_cycles=0,
        status='initializing',valid=False,stopped=False,policy_calls=0,warmup_draws=0,training_updates=0)
    result=dict(status='LOADING',actual_updates_for_job=0,attempted_updates_for_job=0)
    write(folder/'receipt.json',receipt);write(folder/'job_result.json',result)
    def enforce():
        if time.monotonic()-start>reg['max_worker_wall_s'] or (OUT/'STOP').exists():raise RuntimeError('Diagnostic runtime/stop bound; no retry')
    try:
        from tools.validation.run_consistent_sac import select,policy_digest,audit_source_copy
        runtime=select(reg)
        from tools.learning.consistent_sac import load_checkpoint,collect_episode,CollectionError
        from tools.learning.consistent_sac_trial import environment_class
        from tools.learning.noise50_trial import FrozenHeldPolicy,HeldSourceReplay,source_contexts,session_class,verify_passive_channel
        from tools.learning.newton_profile import build_model_xml
        from tools.validation.yaw_pilot import YawContactCase
        from tools.validation.consistent_sac_audit import audit_archive
        trainer=load_checkpoint(reg['source_checkpoint'],expected_digest=reg['source_checkpoint_sha256'],config=reg['config'])
        counts_before=deepcopy(trainer.updater.counts);attempts_before=trainer.update_attempts;replay_before=len(trainer.replay)
        if any(v!=4000 for v in counts_before.values()) or policy_digest(trainer)!=reg['source_policy_sha256']:raise ValueError('Exact frozen F4000 source required')
        source_trainer=audit_source_copy(trainer)
        provider=FrozenHeldPolicy(trainer,job['noise_seed']);source_provider=FrozenHeldPolicy(source_trainer,job['noise_seed'])
        receipt.update(source_checkpoint_sha256=reg['source_checkpoint_sha256'],source_policy_sha256=reg['source_policy_sha256'])
        env=environment_class()();model=model_archive_bytes(build_model_xml(env.profile));(folder/'model_used.xml').write_bytes(model)
        receipt.update(actual_common(env,runtime,model))
        if any(canonical(receipt[k])!=canonical(reg['common'][k]) for k in COMMON):raise ValueError('Common native domain differs')
        Base=session_class(job['passive_yaw_enabled'])
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
                raw.update(policy_calls=provider.policy_calls,warmup_draws=0,behavior_contract=receipt['behavior_contract'],noise_seed=job['noise_seed'])
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
        audited,receipt,proof=audit_archive(folder,reg,job,source_trainer=adapter)
        result['audit_neural_policy_calls']=adapter.policy_calls
        if canonical(adapter.finish())!=canonical(actual_sampler):raise ValueError('Held source endpoint differs')
        if (audited.get('behavior_contract')!=behavior_contract(job['passive_yaw_enabled']) or audited.get('noise_seed')!=job['noise_seed']):raise ValueError('Behavior contract differs')
        proof.update(behavior_version=VERSION,noise_source_replay_verified=True,noise_refreshes=provider.sampler.clock_draw_count,
            passive_channel=verify_passive_channel(audited,job['passive_yaw_enabled']),optimizer_updates=0,replay_publication=False)
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
        rows.append(dict(id=job['id'],complete=j.get('status')=='FINISHED' and s.get('process_exit_confirmed') is True,
            initializations=max(r.get('reset_attempted',0),p.get('reset_attempted',0)),physical_substeps=max(r.get('physical_substeps',0),p.get('physical_substeps',0)),
            cycles=max(r.get('control_cycles',0),p.get('cycles',0)),policy_calls=max(r.get('policy_calls',0),p.get('policy_calls',0)),
            audit_neural_policy_calls=j.get('audit_neural_policy_calls',0),outcome=r.get('outcome'),reason=r.get('final_reason')))
    return dict(episodes=rows,initialization_attempts=sum(r['initializations'] for r in rows),physical_substeps=sum(r['physical_substeps'] for r in rows),
        policy_calls=sum(r['policy_calls'] for r in rows),audit_neural_policy_calls=sum(r['audit_neural_policy_calls'] for r in rows),training_updates=0,
        completed_episodes=sum(r['complete'] for r in rows),counts_exact=all(r['complete'] for r in rows),cumulative_initializations=439+sum(r['initializations'] for r in rows))


def run():
    reg=ready();(OUT/'run').mkdir();write(OUT/'batch_started.json',dict(unix_s=time.time()));start=time.monotonic();status='RUNNING';error=None
    def ledger():
        v=summarize(reg);v.update(status=status,error=error,elapsed_wall_s=time.monotonic()-start);write(OUT/'ledger.json',v);return v
    def launch(job):
        ready();folder=OUT/'run'/job['id'];folder.mkdir()
        return supervise([str(PYTHON),'-B','-X','utf8',str(Path(__file__).resolve()),'--worker',job['id']],folder,timeout=reg['max_worker_wall_s']+180)
    ledger()
    try:
        for offset in (0,2):
            if time.monotonic()-start>reg['max_batch_wall_s']:raise RuntimeError('Batch time bound')
            pair=reg['schedule'][offset:offset+2]
            with ThreadPoolExecutor(max_workers=2) as pool:proofs=list(pool.map(launch,pair))
            ledger()
            for job,proof in zip(pair,proofs):
                result=read(OUT/'run'/job['id']/'job_result.json')
                if proof.get('returncode')!=0 or not proof.get('process_exit_confirmed') or result.get('status')!='FINISHED':raise RuntimeError('Unqualified diagnostic; no retry: '+job['id'])
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
