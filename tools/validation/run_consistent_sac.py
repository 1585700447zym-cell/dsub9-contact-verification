"""One bounded real G1 SAC batch; 4 zero + 4 fresh warmup + 8 online + 4 dev."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.learning.consistent_sac_trial import schedule, summarize_run, MAX_CYCLES, CUMULATIVE_BEFORE
from tools.validation.run_yaw_pilot import read, sha, write, publish_archive, actual_common, model_archive_bytes, supervise

OUT = ROOT/'deliverables/learning_chain/consistent_reference_sac_20261029'
PYTHON = ROOT/'tmp/learning_cpu_20260924/Scripts/python.exe'
RUNTIME = ROOT/'deliverables/learning_chain/b2_repaired_cycle_v2_20260928/runtime.json'
PARENT = ROOT/'deliverables/learning_chain/global_residual_authority_20261028'
REPAIR = ROOT/'deliverables/learning_chain/reference_consistency_20261029'
PLAN = ROOT/'docs/superpowers/plans/2026-10-29-consistent-reference-sac.md'
COMMON = ('dynamic_config','effective_kd','model_xml_sha256','actual_model','runtime')


def canonical(value):
    return json.dumps(value, sort_keys=True, allow_nan=False, separators=(',',':'))


def verify_inputs(pins):
    for name,digest in pins.items():
        target=(ROOT/name).resolve()
        if not target.is_relative_to(ROOT) or sha(target)!=digest:
            raise ValueError('Frozen input differs: '+name)


def policy_digest(trainer):
    digest=hashlib.sha256()
    for name,value in sorted(trainer.updater.policy.state_dict().items()):
        digest.update(name.encode());digest.update(str(value.dtype).encode())
        digest.update(value.detach().cpu().numpy().tobytes())
    return digest.hexdigest()


def select(reg):
    from tools.learning.runtime import select_runtime,verify_runtime,active_package
    select_runtime(RUNTIME,expected_digest=reg['runtime_sha256'])
    return verify_runtime(active_package())


def prepare():
    from tools.learning.consistent_sac import Trainer,learning_config,execution_contract,save_checkpoint
    verify_inputs(read(PARENT/'registration.json')['inputs'])
    repaired=read(REPAIR/'verification.json')
    verify_inputs(repaired['files'])
    if repaired['scientific_cumulative_initializations']!=419:
        raise ValueError('Scientific cost starting point differs')
    OUT.mkdir()  # Never replace a previous or partial batch.
    paths=list((ROOT/'tools').rglob('*.py'))+list((ROOT/'models').rglob('*.xml'))
    paths+=list((ROOT/'assets').rglob('*.stl'))+[RUNTIME,PLAN,REPAIR/'verification.json',
        ROOT/'docs/stage_b/训练合同_v3.md',ROOT/'docs/stage_b/五维残差SAC执行补充合同_v1.md',
        ROOT/'deliverables/learning_chain/b2_newton_sac_preparation_20261016/newton_raw_audit.py',
        ROOT/'deliverables/b2_search_recovery/matrix_v1_7cases/results_index.json']
    pins={}
    for path in sorted(set(paths)):
        name=path.relative_to(ROOT).as_posix();target=OUT/'source_snapshot'/name
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(path.read_bytes());pins[name]=sha(path)
    trainer=Trainer(learning_config())
    initial_policy=policy_digest(trainer)
    initial_digest=save_checkpoint(trainer,OUT/'initial_checkpoint')
    if trainer.update_attempts or trainer.policy_calls or trainer.warmup_draws or len(trainer.replay):
        raise ValueError('A fresh network and empty replay are required')
    parent=read(PARENT/'run/G1_YAW_P15/receipt.json')
    reg=dict(version='consistent_reference_sac_trial_v1',inputs=pins,config=learning_config(),
        execution_contract=execution_contract(),common={key:parent[key] for key in COMMON},
        schedule=schedule(),max_initializations=20,max_physical_substeps=3200000,total_updates=4000,
        cumulative_before=CUMULATIVE_BEFORE,max_worker_wall_s=1800,max_batch_wall_s=21600,
        max_cycles=MAX_CYCLES,retries=0,max_parallel_workers=2,final_test_episodes=0,
        runtime_sha256=sha(RUNTIME),initial_checkpoint_sha256=initial_digest,initial_policy_sha256=initial_policy,
        seed=2026092716,old_replay_reused=False,old_weights_reused=False,
        authorization='User selected 8 SAC online episodes/4000 updates, 20 total initializations on 2026-10-29',
        native_admission='The four matched baseline episodes and four fresh warmups are the only qualification episodes; no extra resets',
        stop_on=['invalid_simulation','unqualified_motion','unqualified_stop','source_audit_save_or_update_failure'],
        comparison='same repaired environment, G1/30s, matched zero-residual vs frozen 4000-update policy; development only')
    write(OUT/'registration.json',reg)
    write(OUT/'preparation.json',dict(ready_for_baseline=True,native_qualification_complete=False,
        formal_optimizer_started=False,registration_sha256=sha(OUT/'registration.json'),
        fresh_initial_policy_sha256=initial_policy,replay_rows=0,physical_steps=0,training_updates=0))
    print(json.dumps(dict(prepared=True,initializations=20,updates=4000,frozen_inputs=len(pins))))


def ready():
    from tools.learning.consistent_sac import learning_config,execution_contract
    reg=read(OUT/'registration.json');prep=read(OUT/'preparation.json')
    if (reg['schedule']!=schedule() or reg['config']!=learning_config()
            or reg['execution_contract']!=execution_contract() or reg['max_initializations']!=20
            or reg['total_updates']!=4000 or reg['cumulative_before']!=419
            or prep['registration_sha256']!=sha(OUT/'registration.json')):
        raise ValueError('Registered budget/config/implementation binding differs')
    verify_inputs(reg['inputs']);return reg


def source_checkpoint(reg,job):
    stage=job['stage']
    if stage=='baseline': return None,None
    candidates=[row for row in reg['schedule'] if row['stage'] in ('warmup','online')]
    if stage=='development': previous=candidates[-1]
    else:
        index=next(i for i,row in enumerate(candidates) if row['id']==job['id'])
        if index==0:return OUT/'initial_checkpoint',reg['initial_checkpoint_sha256']
        previous=candidates[index-1]
    folder=OUT/'run'/previous['id'];result=read(folder/'job_result.json')
    if result['status']!='FINISHED': raise ValueError('Complete previous audited boundary required')
    return folder/'checkpoint',result['checkpoint_sha256']


def audit_source_copy(trainer):
    """Copy the validated source policy/RNG, without duplicating its large replay."""
    from tools.learning.consistent_sac import Trainer
    source=Trainer(trainer.config)
    source.updater._restore(deepcopy(trainer.updater._snapshot()))
    source.warm_rng.bit_generator.state=deepcopy(trainer.warm_rng.bit_generator.state)
    source.policy_calls,source.warmup_draws=trainer.policy_calls,trainer.warmup_draws
    return source


def worker(job_id):
    reg=ready();job=next(job for job in reg['schedule'] if job['id']==job_id)
    folder=OUT/'run'/job_id
    with (folder/'worker.claim').open('x') as claim:claim.write(str(os.getpid()))
    receipt=dict(case_id=job_id,stage=job['stage'],execution_contract=reg['execution_contract'],
        status='initializing',reset_attempted=0,reset_completed=0,physical_substeps=0,control_cycles=0,
        valid=False,stopped=False,policy_calls=0,warmup_draws=0,training_updates=0,
        registration_sha256=sha(OUT/'registration.json'),case=job['case'])
    result=dict(status='LOADING',actual_updates_for_job=0,attempted_updates_for_job=0)
    write(folder/'receipt.json',receipt);write(folder/'job_result.json',result)
    env=session=trainer=source_trainer=None;raw={};started=time.monotonic()
    before_updates=before_calls=before_draws=before_attempts=0
    def enforce():
        if (time.monotonic()-started>reg['max_worker_wall_s']
                or time.time()-read(OUT/'batch_started.json')['unix_s']>reg['max_batch_wall_s']
                or (OUT/'STOP').exists()):
            raise RuntimeError('Batch runtime/stop bound; no retry')
    try:
        runtime=select(reg)  # Select the pinned native package before any environment import.
        from tools.learning.consistent_sac import load_checkpoint,save_checkpoint,collect_episode,CollectionError
        from tools.learning.consistent_sac_trial import environment_class,session_class
        from tools.validation.consistent_sac_audit import audit_archive
        from tools.learning.newton_profile import build_model_xml
        from tools.validation.yaw_pilot import YawContactCase
        if job['stage'] in ('warmup','online','development'):
            native=read(OUT/'native_reference_qualification.json')
            if not native['verified'] or native['registration_sha256']!=sha(OUT/'registration.json'):
                raise ValueError('Matched native baselines not qualified')
        if job['stage'] in ('online','development'):
            admission=read(OUT/'learning_admission.json')
            if not admission['verified'] or admission['registration_sha256']!=sha(OUT/'registration.json'):
                raise ValueError('New warmup domain not admitted')
        source,digest=source_checkpoint(reg,job)
        receipt['source_checkpoint_sha256']=digest
        if source is not None:
            trainer=load_checkpoint(source,expected_digest=digest,config=reg['config'])
            before_updates=trainer.updater.counts['critic'];before_attempts=trainer.update_attempts
            before_calls,before_draws=trainer.policy_calls,trainer.warmup_draws
            expected=4000 if job['stage']=='development' else sum(row['updates_after'] for row in reg['schedule'][:reg['schedule'].index(job)])
            if before_updates!=expected:raise ValueError('Source update boundary differs')
            source_trainer=audit_source_copy(trainer)
            receipt['source_policy_sha256']=policy_digest(trainer)
        env=environment_class()();model_bytes=model_archive_bytes(build_model_xml(env.profile))
        (folder/'model_used.xml').write_bytes(model_bytes)
        receipt.update(actual_common(env,runtime,model_bytes))
        if any(canonical(receipt[key])!=canonical(reg['common'][key]) for key in COMMON):
            raise ValueError('Common physical/runtime domain differs')
        Base=session_class()
        class BoundedSession(Base):
            def advance_cycle(self,action):
                enforce();cycle=super().advance_cycle(action)
                if self.cycle_id%100==0:
                    write(folder/'progress.json',dict(cycles=self.cycle_id,simulation_s=self.cycle_id*.002,
                        physical_substeps=env.physical_steps,reset_attempted=1,
                        policy_calls=0 if trainer is None else trainer.policy_calls-before_calls,
                        warmup_draws=0 if trainer is None else trainer.warmup_draws-before_draws,
                        phase=cycle.next_snapshot.controller_state['phase']))
                return cycle
        session=BoundedSession(env);point=YawContactCase(**job['case'])
        receipt.update(reset_attempted=1,seed=job['seed']);write(folder/'receipt.json',receipt)
        result['status']='COLLECTING';write(folder/'job_result.json',result)
        try:
            if trainer is None:
                raw=collect_episode(session,point,policy=lambda obs:[0.]*5,seed=job['seed'],max_cycles=MAX_CYCLES)
                raw.update(policy_calls=0,warmup_draws=0)
            else:
                raw=trainer.collect(session,point,seed=job['seed'],max_cycles=MAX_CYCLES,
                    warmup=job['stage']=='warmup',deterministic=job['stage']=='development')
        except CollectionError as exc:
            raw=exc.archive;raise
        finally:
            if env is not None:
                receipt.update(physical_substeps=getattr(env,'physical_steps',0),control_cycles=getattr(session,'cycle_id',0),
                    guard_facts=env.guard_facts,reference_checks=env.reference_checks,
                    reference_corrections=env.reference_envelope_corrections)
            if trainer is not None:
                receipt.update(policy_calls=trainer.policy_calls-before_calls,warmup_draws=trainer.warmup_draws-before_draws)
            if raw.get('outcome'):
                receipt.update(status='error' if raw.get('error') else 'finished',reset_completed=raw['cost']['initializations_completed'],
                    valid=raw['outcome']['simulation_valid'],stopped=raw['outcome']['physical_stopped'],
                    outcome=raw['outcome']['task_outcome'],final_reason=getattr(session,'reason',None),
                    finish_criteria=session.finish_criteria,initialization_guard_config=asdict(env.guard_config),
                    task_time_s=getattr(session,'task_end_time',None),stop_time_s=getattr(session,'stop_time',None),
                    audit_end_time_s=float(env.data.time) if hasattr(env,'data') else None)
                if getattr(session,'controller',None) is not None:
                    receipt.update(controller_config=asdict(session.controller.config),controller_metadata=session.controller.metadata())
            receipt['elapsed_wall_s']=time.monotonic()-started
            publish_archive(folder,raw,receipt)
        raw=None
        result['status']='AUDITING';write(folder/'job_result.json',result)
        raw,receipt,audit=audit_archive(folder,reg,job,source_trainer=source_trainer)
        if source_trainer is not None:
            if (not source_trainer.updater.rng_state.equal(trainer.updater.rng_state)
                    or canonical(source_trainer.warm_rng.bit_generator.state)!=canonical(trainer.warm_rng.bit_generator.state)
                    or source_trainer.policy_calls!=trainer.policy_calls or source_trainer.warmup_draws!=trainer.warmup_draws):
                raise ValueError('Audited action RNG endpoint differs from actual collection')
            audit['source_rng_endpoint_verified']=True
        write(folder/'audit.json',audit)
        result['audit_neural_policy_calls']=0 if source_trainer is None else source_trainer.policy_calls-before_calls
        result['audit_warmup_replays']=0 if source_trainer is None else source_trainer.warmup_draws-before_draws
        source_trainer=None
        if job['publish']:
            publication=trainer.publish(job_id,raw['transitions'],outcome=dict(raw['outcome'],valid_for_learning=True),training_admitted=True)
            write(folder/'publication.json',dict(publication,archive_sha256=receipt['archive_sha256'],
                audit_sha256=sha(folder/'audit.json'),registration_sha256=sha(OUT/'registration.json')))
        raw=None
        result['status']='UPDATING' if job['updates_after'] else 'SAVING';write(folder/'job_result.json',result)
        telemetry=[]
        for _ in range(job['updates_after']):
            enforce();log=trainer.update_from_replay();telemetry.append(log)
            if len(telemetry)%25==0:
                write(folder/'update_progress.json',dict(actual_updates_for_job=trainer.updater.counts['critic']-before_updates,
                    attempted_updates_for_job=trainer.update_attempts-before_attempts,alpha=log['alpha_after']))
        if telemetry:write(folder/'update_telemetry.json',telemetry)
        if trainer is not None:
            result.update(policy_sha256=policy_digest(trainer),updater_counts=trainer.updater.counts,
                replay_rows=len(trainer.replay),alpha=float(trainer.updater.log_alpha.exp().detach()))
            if job['publish']:
                result['checkpoint_sha256']=save_checkpoint(trainer,folder/'checkpoint')
            elif policy_digest(trainer)!=receipt['source_policy_sha256']:
                raise ValueError('Frozen evaluation changed policy parameters')
        result.update(status='FINISHED',outcome=receipt['outcome'],final_reason=receipt['final_reason'])
        verify_inputs(reg['inputs'])
    except BaseException as exc:
        result.update(status='ERROR',error=repr(exc))
        if receipt['status']!='finished':
            receipt.update(status='error',error=repr(exc),elapsed_wall_s=time.monotonic()-started)
            if env is not None:
                receipt.update(physical_substeps=getattr(env,'physical_steps',0),control_cycles=getattr(session,'cycle_id',0),
                    guard_facts=env.guard_facts,reference_checks=env.reference_checks)
            write(folder/'receipt.json',receipt)
        raise
    finally:
        if source_trainer is not None:
            result.update(audit_neural_policy_calls=source_trainer.policy_calls-before_calls,
                          audit_warmup_replays=source_trainer.warmup_draws-before_draws)
        if trainer is not None:
            result.update(actual_updates_for_job=trainer.updater.counts['critic']-before_updates,
                          attempted_updates_for_job=trainer.update_attempts-before_attempts)
        result['elapsed_wall_s']=time.monotonic()-started;write(folder/'job_result.json',result)


def qualification(reg,stage,filename):
    folders=[OUT/'run'/job['id'] for job in reg['schedule'] if job['stage']==stage]
    proofs=[]
    for folder in folders:
        audit,receipt,result=[read(folder/name) for name in ('audit.json','receipt.json','job_result.json')]
        if not audit['verified'] or result['status']!='FINISHED' or not receipt['valid'] or not receipt['stopped']:
            raise ValueError('Complete accepted stage required')
        proofs.append(dict(id=folder.name,archive_sha256=receipt['archive_sha256'],audit_sha256=sha(folder/'audit.json'),
            reference_checks=receipt['reference_checks']))
    if sum(proof['reference_checks']['feasible_checks'] for proof in proofs)==0:
        raise ValueError('Reference repair was not exercised in the registered native stage')
    write(OUT/filename,dict(verified=True,stage=stage,registration_sha256=sha(OUT/'registration.json'),episodes=proofs))


def final_summary(ledger):
    rows=ledger['episodes'];groups={stage:[row for row in rows if row['stage']==stage and row['complete']]
        for stage in ('baseline','warmup','online','development')}
    summary=dict(status=ledger['status'],initializations=ledger['initialization_attempts'],physical_substeps=ledger['physical_substeps'],
        updates=ledger['training_updates'],counts_exact=ledger['counts_exact'],cumulative_initializations=ledger['cumulative_initializations'],
        baseline_completed=len(groups['baseline']),baseline_successes=sum(row['outcome']=='FULL_SUCCESS' for row in groups['baseline']),
        development_completed=len(groups['development']),development_successes=sum(row['outcome']=='FULL_SUCCESS' for row in groups['development']),
        episodes=rows,error=ledger.get('error'),no_final_test=True)
    write(OUT/'summary.json',summary)


def run():
    reg=ready();(OUT/'run').mkdir();write(OUT/'batch_started.json',dict(unix_s=time.time()))
    started=time.monotonic();status='RUNNING';error=None
    def ledger():
        data=summarize_run(OUT/'run');data.update(status=status,error=error,elapsed_wall_s=time.monotonic()-started,
            registration_sha256=sha(OUT/'registration.json'))
        write(OUT/'ledger.json',data);return data
    def launch(job):
        ready()
        if time.monotonic()-started>reg['max_batch_wall_s'] or (OUT/'STOP').exists():raise RuntimeError('Batch bound before next job')
        folder=OUT/'run'/job['id'];folder.mkdir()
        return supervise([str(PYTHON),'-B','-X','utf8',str(Path(__file__).resolve()),'--worker',job['id']],
            folder,timeout=reg['max_worker_wall_s']+180)
    def checked(job,proof):
        folder=OUT/'run'/job['id'];result=read(folder/'job_result.json') if (folder/'job_result.json').exists() else {}
        ledger()
        if proof.get('returncode')!=0 or not proof.get('process_exit_confirmed') or result.get('status')!='FINISHED':
            raise RuntimeError('Unqualified job; batch stopped without retry: '+job['id'])
    ledger()
    try:
        for stage in ('baseline','warmup','online','development'):
            jobs=[job for job in reg['schedule'] if job['stage']==stage]
            if stage in ('baseline','development'):
                for start in range(0,len(jobs),2):
                    pair=jobs[start:start+2]
                    with ThreadPoolExecutor(max_workers=2) as pool:proofs=list(pool.map(launch,pair))
                    for job,proof in zip(pair,proofs):checked(job,proof)
            else:
                for job in jobs:checked(job,launch(job))
            if stage=='baseline':qualification(reg,stage,'native_reference_qualification.json')
            if stage=='warmup':qualification(reg,stage,'learning_admission.json')
            if stage=='online':
                final=OUT/'run'/jobs[-1]['id'];result=read(final/'job_result.json')
                if result['updater_counts']['critic']!=4000:raise ValueError('Final update count differs')
                write(OUT/'frozen_policy.json',dict(checkpoint=str(final/'checkpoint'),checkpoint_sha256=result['checkpoint_sha256'],
                    policy_sha256=result['policy_sha256'],updates=4000))
            print(json.dumps(dict(stage=stage,completed=True,updates=ledger()['training_updates'])),flush=True)
        status='COMPLETED'
    except BaseException as exc:
        status='STOPPED';error=repr(exc);raise
    finally:final_summary(ledger())


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare',action='store_true');group.add_argument('--check-ready',action='store_true')
    group.add_argument('--run',action='store_true');group.add_argument('--launch',action='store_true');group.add_argument('--worker')
    args=parser.parse_args(argv)
    if args.prepare:prepare()
    elif args.check_ready:reg=ready();select(reg);print('Ready for registered native baselines; no new physics or updates.')
    elif args.worker:worker(args.worker)
    elif args.run:run()
    else:
        ready()
        with (OUT/'launcher.claim').open('x'):pass
        proof=dict(started=False,process_exit_confirmed=False,returncode=None)
        try:
            with (OUT/'launcher.log').open('xb') as log:
                proc=subprocess.Popen([str(PYTHON),'-B','-X','utf8',str(Path(__file__).resolve()),'--run'],cwd=ROOT,
                    stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                proof.update(started=True,pid=proc.pid,supervisor_pid=os.getpid());write(OUT/'process_started.json',proof)
                try:proof['returncode']=proc.wait()
                finally:proof['process_exit_confirmed']=proc.poll() is not None
        finally:write(OUT/'process_exit.json',proof)
        return proof['returncode']
    return 0


if __name__=='__main__':raise SystemExit(main())
