"""Explicit F4000 migration checks and new simulation/continuation batches.

Default action checks saved state only. No physics, policy prediction or update
is performed unless --run (or its supervised private --worker) is selected.
"""
import argparse
from dataclasses import asdict
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from tools.migration.package import digest,read,write_new,load_paths


def parser():
    p=argparse.ArgumentParser(description=__doc__)
    g=p.add_mutually_exclusive_group()
    for name in ('check','prepare','run','worker'):
        g.add_argument('--'+name,action='store_const',dest='action',const=name)
    p.set_defaults(action='check')
    p.add_argument('--destination',type=Path,default=ROOT/'.migration')
    p.add_argument('--output',type=Path)
    p.add_argument('--purpose',choices=['simulation','continuation'],default='simulation')
    p.add_argument('--episodes',type=int,default=1)
    p.add_argument('--updates-per-episode',type=int,default=0)
    p.add_argument('--job-id')
    p.add_argument('--compile-model',action='store_true')
    return p


def validate_request(args):
    if args.action in ('prepare','run','worker') and args.output is None:
        raise ValueError('Explicit output batch directory required')
    if args.action=='prepare':
        if not 1<=args.episodes<=8:raise ValueError('Episode budget must be 1..8')
        if args.purpose=='continuation' and not 1<=args.updates_per_episode<=500:
            raise ValueError('Continuation update budget must be 1..500 per episode')
        if args.purpose=='simulation' and args.updates_per_episode!=0:
            raise ValueError('Simulation has zero optimizer updates')
    return args


def activate(paths):
    """Use the unmodified source version that created the complete checkpoint."""
    engine=Path(paths['engine']).resolve()
    forbidden=[n for n in sys.modules if n.startswith(('tools.learning','tools.dynamics','tools.model','tools.validation','tools.control'))]
    if forbidden:raise RuntimeError('Start a fresh process before selecting the frozen engine')
    sys.path.insert(0,str(engine));importlib.invalidate_caches()
    from tools.learning.runtime import select_runtime,verify_runtime,active_package
    select_runtime(paths['runtime_record'],expected_digest=paths['runtime_record_sha256'])
    runtime=verify_runtime(active_package())
    from tools.learning import consistent_sac as sac
    if not Path(sac.__file__).resolve().is_relative_to(engine):
        raise RuntimeError('Frozen engine was shadowed by the working source')
    from tools.model import layered_task
    if layered_task.GEOMETRY_TOLERANCE_M!=1e-9:raise ValueError('Original F4000 1nm protocol required')
    source=read(Path(paths['root'])/'source/registration.json')
    if source['config']!=sac.learning_config():raise ValueError('Original SAC configuration differs')
    for rel,expected in source['inputs'].items():
        if digest(engine/rel)!=expected:raise ValueError('Frozen source input differs: '+rel)
    for filename in ('native_reference_qualification.json','learning_admission.json'):
        evidence=read(Path(paths['root'])/'source'/filename)
        if not evidence['verified'] or evidence['registration_sha256']!=digest(Path(paths['root'])/'source/registration.json'):
            raise ValueError('Original admitted-domain evidence differs')
    return sac,runtime,source


def restore_trainer(paths,sac,source,checkpoint=None,expected=None):
    frozen=read(Path(paths['root'])/'source/frozen_policy.json')
    return sac.load_checkpoint(checkpoint or paths['checkpoint'],
        expected_digest=expected or frozen['checkpoint_sha256'],config=source['config'])


def check(paths,compile_model=False):
    sac,runtime,source=activate(paths)
    trainer=restore_trainer(paths,sac,source)
    from tools.validation.run_consistent_sac import policy_digest
    frozen=read(Path(paths['root'])/'source/frozen_policy.json')
    if trainer.update_attempts!=4000 or policy_digest(trainer)!=frozen['policy_sha256']:
        raise ValueError('Restored F4000 state differs')
    if compile_model:
        import mujoco
        previous=Path.cwd()
        try:
            os.chdir(paths['engine'])
            model=mujoco.MjModel.from_xml_string((Path(paths['root'])/'source/model_used.xml').read_text(encoding='utf-8'))
        finally:os.chdir(previous)
        if model.nu!=0 or model.nv!=6:raise ValueError('Unexpected migrated model')
    return dict(verified=True,updates=trainer.updater.counts,replay_rows=len(trainer.replay),
        policy_sha256=frozen['policy_sha256'],runtime_version=runtime['version'],
        old_success_tolerance_m=1e-9,default_current_source_tolerance_m=1e-8,
        model_compiled=bool(compile_model),physics_resets=0,physics_steps=0,
        neural_inference=0,new_optimizer_updates=0)


def prepare(args,paths):
    sac,runtime,source=activate(paths)
    frozen=read(Path(paths['root'])/'source/frozen_policy.json')
    from tools.learning.five_axis_preparation import cases
    points=cases();jobs=[]
    for i in range(args.episodes):
        jobs.append(dict(id=f'{i+1:02d}_'+points[i%4]['name'],stage='online' if args.purpose=='continuation' else 'development',
            case=points[i%4],seed=2026110201+i,publish=args.purpose=='continuation',updates_after=args.updates_per_episode))
    common=dict(source['common'],runtime=runtime)
    reg=dict(version='f4000_original_protocol_continuation_v1',purpose=args.purpose,
        package_sha256=paths['package_sha256'],paths=paths,config=source['config'],
        execution_contract=source['execution_contract'],common=common,schedule=jobs,
        initial_checkpoint=paths['checkpoint'],initial_checkpoint_sha256=frozen['checkpoint_sha256'],
        updates_before=4000,updates_budget=args.episodes*args.updates_per_episode,
        initializations_budget=args.episodes,physical_substeps_budget=args.episodes*160000,
        max_worker_wall_s=3600,old_success_tolerance_m=1e-9,exploration_period_s=.002,
        migration_publication_scientific_reference=443,new_batch_costs_recorded_separately=True,
        no_final_test=True,retries=0,
        admission='Inherit byte-identical original qualified domain and checkpoint; native per-episode audit remains mandatory',
        launcher_sha256=digest(Path(__file__)))
    output=args.output.resolve()
    if output==ROOT or output.is_relative_to(Path(paths['root'])) or output in (Path(paths['engine']),Path(paths['checkpoint'])):
        raise ValueError('Output must be a new batch outside restored source/state')
    output.mkdir(parents=True,exist_ok=False)
    write_new(output/'registration.json',reg)
    write_new(output/'prepared.json',dict(registration_sha256=digest(output/'registration.json')))
    print(json.dumps(dict(prepared=True,output=str(output),jobs=len(jobs),updates_budget=reg['updates_budget'],started=False),ensure_ascii=False))


def verified_registration(args,paths):
    file=args.output.resolve()/'registration.json'
    if digest(file)!=read(file.with_name('prepared.json'))['registration_sha256']:
        raise ValueError('Prepared registration digest changed')
    reg=read(file)
    if reg['version']!='f4000_original_protocol_continuation_v1' or reg['package_sha256']!=paths['package_sha256']:
        raise ValueError('Prepared batch and restored package differ')
    if reg['paths']!=paths or reg['launcher_sha256']!=digest(Path(__file__)):
        raise ValueError('Batch moved or launcher changed; prepare a new batch')
    source=read(Path(paths['root'])/'source/registration.json')
    allowed=[x['case'] for x in source['schedule']]
    jobs=reg['schedule'];online=reg['purpose']=='continuation'
    if reg['purpose'] not in ('simulation','continuation') or not 1<=len(jobs)<=8:
        raise ValueError('Registered episode budget differs')
    for i,j in enumerate(jobs):
        if (j['case'] not in allowed or j['stage']!=('online' if online else 'development')
                or j['publish'] is not online or j['id']!=f'{i+1:02d}_'+j['case']['name']
                or type(j['updates_after']) is not int or type(j['seed']) is not int
                or (not 1<=j['updates_after']<=500 if online else j['updates_after']!=0)):
            raise ValueError('Registered case/stage/update budget differs')
    if (reg['initializations_budget']!=len(jobs) or reg['physical_substeps_budget']!=len(jobs)*160000
            or reg['updates_budget']!=sum(x['updates_after'] for x in jobs)
            or reg['config']!=source['config'] or reg['execution_contract']!=source['execution_contract']
            or reg['old_success_tolerance_m']!=1e-9 or reg['exploration_period_s']!=.002
            or reg['retries']!=0 or reg['no_final_test'] is not True):
        raise ValueError('Registered protocol or total budget differs')
    return reg


def collection_receipt(receipt,env,session,trainer,raw,before_calls,before_draws):
    receipt.update(physical_substeps=getattr(env,'physical_steps',0),control_cycles=getattr(session,'cycle_id',0),
        guard_facts=getattr(env,'guard_facts',{}),reference_checks=getattr(env,'reference_checks',{}),
        reference_corrections=getattr(env,'reference_envelope_corrections',0),
        policy_calls=trainer.policy_calls-before_calls,warmup_draws=trainer.warmup_draws-before_draws)
    if raw.get('outcome'):
        guard=getattr(env,'guard_config',None)
        receipt.update(status='error' if raw.get('error') else 'finished',
            reset_completed=raw['cost']['initializations_completed'],
            valid=raw['outcome']['simulation_valid'],stopped=raw['outcome']['physical_stopped'],
            outcome=raw['outcome']['task_outcome'],final_reason=getattr(session,'reason',None),
            finish_criteria=getattr(session,'finish_criteria',None),
            initialization_guard_config=asdict(guard) if guard is not None else None,
            task_time_s=getattr(session,'task_end_time',None),stop_time_s=getattr(session,'stop_time',None),
            audit_end_time_s=float(env.data.time) if hasattr(env,'data') else None)
        controller=getattr(session,'controller',None)
        if controller is not None:
            receipt.update(controller_config=asdict(controller.config),controller_metadata=controller.metadata())


def final_costs(result,receipt,trainer,source_trainer,before,before_attempts,before_calls,before_draws):
    if trainer is not None:
        result.update(actual_updates_for_job=trainer.updater.counts['critic']-before,
            attempted_updates_for_job=trainer.update_attempts-before_attempts)
        receipt.update(policy_calls=trainer.policy_calls-before_calls,warmup_draws=trainer.warmup_draws-before_draws)
    if source_trainer is not None:
        result.update(audit_neural_policy_calls=source_trainer.policy_calls-before_calls,
            audit_warmup_replays=source_trainer.warmup_draws-before_draws)


def worker(args,paths):
    reg=verified_registration(args,paths)
    job=next(j for j in reg['schedule'] if j['id']==args.job_id)
    sac,runtime,source=activate(paths)
    from tools.validation.run_consistent_sac import audit_source_copy,policy_digest
    from tools.validation.run_yaw_pilot import actual_common,model_archive_bytes,publish_archive
    from tools.learning.consistent_sac_trial import environment_class,session_class
    from tools.learning.newton_profile import build_model_xml
    from tools.validation.yaw_pilot import YawContactCase
    from tools.validation.consistent_sac_audit import audit_archive
    from tools.learning.five_axis_preparation import canonical
    output=args.output.resolve();folder=output/'run'/job['id']
    write_new(folder/'worker.claim',dict(pid=os.getpid()))
    index=reg['schedule'].index(job)
    prior=reg['schedule'][index-1] if index and job['publish'] else None
    if prior:
        prior_result=read(output/'run'/prior['id']/'job_result.json')
        if prior_result['status']!='FINISHED':raise ValueError('Previous complete checkpoint required')
        checkpoint=output/'run'/prior['id']/'checkpoint';expected=prior_result['checkpoint_sha256']
    else:checkpoint=Path(reg['initial_checkpoint']);expected=reg['initial_checkpoint_sha256']
    receipt=dict(case_id=job['id'],stage=job['stage'],execution_contract=reg['execution_contract'],
        status='initializing',reset_attempted=0,reset_completed=0,physical_substeps=0,control_cycles=0,
        valid=False,stopped=False,policy_calls=0,warmup_draws=0,training_updates=0,
        case=job['case'],seed=job['seed'],source_checkpoint_sha256=expected,
        registration_sha256=digest(output/'registration.json'))
    result=dict(status='LOADING',actual_updates_for_job=0,attempted_updates_for_job=0)
    def save(name,value):
        target=folder/name;temp=folder/(name+'.tmp')
        temp.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2)+'\n',encoding='utf-8')
        os.replace(temp,target)
    save('receipt.json',receipt);save('job_result.json',result)
    trainer=env=session=source_trainer=None;raw={};started=time.monotonic()
    before=before_attempts=before_calls=before_draws=0
    def enforce():
        if time.monotonic()-started>reg['max_worker_wall_s'] or (output/'STOP').exists():
            raise RuntimeError('Worker time/STOP bound; no automatic retry')
    try:
        trainer=restore_trainer(paths,sac,source,checkpoint,expected)
        before=trainer.updater.counts['critic'];before_attempts=trainer.update_attempts
        before_calls,before_draws=trainer.policy_calls,trainer.warmup_draws
        if before!=4000+sum(j['updates_after'] for j in reg['schedule'][:index]):
            raise ValueError('Complete source update boundary differs')
        source_trainer=audit_source_copy(trainer)
        receipt['source_policy_sha256']=policy_digest(trainer)
        env=environment_class()();model=model_archive_bytes(build_model_xml(env.profile))
        (folder/'model_used.xml').write_bytes(model)
        receipt.update(actual_common(env,runtime,model))
        if any(canonical(receipt[k])!=canonical(reg['common'][k]) for k in reg['common']):
            raise ValueError('Registered native domain differs')
        Base=session_class()
        class Session(Base):
            def advance_cycle(self,action):
                enforce();cycle=super().advance_cycle(action)
                if self.cycle_id%100==0:
                    save('progress.json',dict(cycles=self.cycle_id,simulation_s=self.cycle_id*.002,
                        physical_substeps=env.physical_steps,reset_attempted=1,
                        policy_calls=trainer.policy_calls-before_calls,
                        phase=cycle.next_snapshot.controller_state['phase']))
                return cycle
        session=Session(env);receipt['reset_attempted']=1
        save('receipt.json',receipt);result['status']='COLLECTING';save('job_result.json',result)
        try:
            raw=trainer.collect(session,YawContactCase(**job['case']),seed=job['seed'],
                max_cycles=16000,warmup=False,deterministic=not job['publish'])
        except sac.CollectionError as exc:
            raw=exc.archive;raise
        finally:
            collection_receipt(receipt,env,session,trainer,raw,before_calls,before_draws)
            publish_archive(folder,raw,receipt)
        raw=None;result['status']='AUDITING';save('job_result.json',result)
        raw,receipt,audit=audit_archive(folder,reg,job,source_trainer=source_trainer)
        if (not source_trainer.updater.rng_state.equal(trainer.updater.rng_state)
                or canonical(source_trainer.warm_rng.bit_generator.state)!=canonical(trainer.warm_rng.bit_generator.state)
                or source_trainer.policy_calls!=trainer.policy_calls):
            raise ValueError('Audited action/RNG endpoint differs')
        save('audit.json',audit)
        result['audit_neural_policy_calls']=source_trainer.policy_calls-before_calls;source_trainer=None
        if job['publish']:
            published=trainer.publish(job['id'],raw['transitions'],
                outcome=dict(raw['outcome'],valid_for_learning=True),training_admitted=True)
            save('publication.json',dict(published,archive_sha256=receipt['archive_sha256'],audit_sha256=digest(folder/'audit.json')))
        raw=None;result['status']='UPDATING' if job['updates_after'] else 'SAVING';save('job_result.json',result)
        telemetry=[]
        for _ in range(job['updates_after']):
            enforce();telemetry.append(trainer.update_from_replay())
            if len(telemetry)%25==0:save('update_progress.json',dict(actual_updates_for_job=len(telemetry)))
        if telemetry:save('update_telemetry.json',telemetry)
        if job['publish']:result['checkpoint_sha256']=sac.save_checkpoint(trainer,folder/'checkpoint')
        elif policy_digest(trainer)!=receipt['source_policy_sha256']:
            raise ValueError('Zero-update simulation changed policy weights')
        result.update(status='FINISHED',outcome=receipt['outcome'],final_reason=receipt['final_reason'],
            policy_sha256=policy_digest(trainer),updater_counts=trainer.updater.counts,replay_rows=len(trainer.replay))
        load_paths(args.destination)  # Recheck the restored immutable package before accepting the boundary.
    except BaseException as exc:
        result.update(status='ERROR',error=repr(exc));receipt.update(error=repr(exc))
        if receipt.get('status')!='finished':receipt['status']='error'
        if env is not None:
            receipt.update(physical_substeps=getattr(env,'physical_steps',0),control_cycles=getattr(session,'cycle_id',0))
        save('receipt.json',receipt);raise
    finally:
        final_costs(result,receipt,trainer,source_trainer,before,before_attempts,before_calls,before_draws)
        save('receipt.json',receipt)
        result['elapsed_wall_s']=time.monotonic()-started;save('job_result.json',result)


def recorded_costs(output):
    def optional(p):return read(p) if p.exists() else {}
    counts=dict(new_initializations=0,new_physical_substeps=0,new_optimizer_updates=0,
        attempted_optimizer_updates=0,neural_policy_calls=0,audit_neural_policy_calls=0,
        counts_are_recorded_lower_bounds=False)
    for folder in (Path(output)/'run').iterdir():
        if not folder.is_dir():continue
        receipt=optional(folder/'receipt.json');progress=optional(folder/'progress.json')
        job=optional(folder/'job_result.json');updates=optional(folder/'update_progress.json')
        counts['new_initializations']+=max(receipt.get('reset_attempted',0),progress.get('reset_attempted',0))
        counts['new_physical_substeps']+=max(receipt.get('physical_substeps',0),progress.get('physical_substeps',0))
        counts['new_optimizer_updates']+=max(job.get('actual_updates_for_job',0),updates.get('actual_updates_for_job',0))
        counts['attempted_optimizer_updates']+=max(job.get('attempted_updates_for_job',0),updates.get('actual_updates_for_job',0))
        counts['neural_policy_calls']+=max(receipt.get('policy_calls',0),progress.get('policy_calls',0))
        counts['audit_neural_policy_calls']+=job.get('audit_neural_policy_calls',0)
        if job.get('status')!='FINISHED':counts['counts_are_recorded_lower_bounds']=True
    return counts


def run(args,paths):
    reg=verified_registration(args,paths);output=args.output.resolve()
    write_new(output/'batch_started.json',dict(unix_s=time.time(),purpose=reg['purpose']))
    (output/'run').mkdir();results=[];status='RUNNING';error=None
    def summary():
        value=dict(status=status,error=error,completed=len(results),
            **recorded_costs(output),
            updates_before=4000,results=results,no_final_test=True)
        p=output/'summary.json';p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    try:
        for job in reg['schedule']:
            if (output/'STOP').exists():raise RuntimeError('STOP file present; no automatic retry')
            folder=output/'run'/job['id'];folder.mkdir()
            log=folder/'worker.log'
            command=[sys.executable,'-B',str(Path(__file__).resolve()),'--worker','--job-id',job['id'],
                '--destination',paths['root'],'--output',str(output)]
            proc=None;proof=dict(started=False,process_exit_confirmed=False,returncode=None)
            try:
                with log.open('xb') as stream:
                    proc=subprocess.Popen(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,
                        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    proof.update(started=True,pid=proc.pid)
                    try:code=proc.wait(timeout=reg['max_worker_wall_s']+180)
                    except BaseException as exc:
                        proof['supervision_error']=repr(exc);proc.kill();code=proc.wait();raise
                    finally:proof.update(returncode=proc.returncode,process_exit_confirmed=proc.returncode is not None)
            finally:write_new(folder/'process_exit.json',proof)
            if code:raise RuntimeError('Worker failed; saved evidence retained, no retry: '+job['id'])
            result=read(output/'run'/job['id']/'job_result.json')
            if result['status']!='FINISHED':raise RuntimeError('Worker boundary not accepted')
            results.append(result);summary()
        status='COMPLETED'
    except BaseException as exc:error=repr(exc);status='STOPPED';raise
    finally:summary()


def main(argv=None):
    args=validate_request(parser().parse_args(argv));paths=load_paths(args.destination)
    if args.action=='check':print(json.dumps(check(paths,args.compile_model),ensure_ascii=False))
    elif args.action=='prepare':prepare(args,paths)
    elif args.action=='worker':worker(args,paths)
    else:run(args,paths)


if __name__=='__main__':main()
