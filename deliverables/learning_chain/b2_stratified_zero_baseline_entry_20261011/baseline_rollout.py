"""One admitted zero-residual episode; scientific imports are deferred."""
from dataclasses import asdict
import math
from pathlib import Path
import sys
import time

OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT))
from scope_contract import ROOT,LIMITS,SEED,read,write,digest,case_kwargs,check_pose,check_initial_state,frozen_module


def reset_once(session,case,point,receipt,run,config):
    if receipt.get('reset_attempted')!=0 or receipt.get('reset_completed')!=0:
        raise ValueError('A reserved attempt permits exactly one reset')
    receipt['reset_attempted']=1;write(Path(run)/'receipt.json',receipt)
    snapshot=session.reset(case,seed=SEED)
    receipt['reset_completed']=1;write(Path(run)/'receipt.json',receipt)
    receipt['initial_audit']=check_initial_state(point,session.initial_trace_row,config['common'],session.env.guard_facts)
    write(Path(run)/'receipt.json',receipt)
    return snapshot


def serialize_clearance(value):
    if value==float('-inf'):return dict(value_m=None,status='no_main_overlap')
    if not math.isfinite(value):raise ValueError('Invalid saved-pose clearance')
    return dict(value_m=float(value),status='finite')


def audit_baseline(raw,config):
    index=raw['case_index']
    if type(index) is not int or not 0<=index<25:raise ValueError('Registered matrix index required')
    point=config['cases'][index]
    if raw['case']!=point or raw['case_id']!=point['id'] or raw['simulation_case']!=case_kwargs(point):
        raise ValueError('Actual episode and registry differ')
    check_pose(point,raw['trace'][0])
    if (raw['role']!='pure_B2' or raw['comparison_key']!=config['common_key'] or
        raw['policy_calls']!=0 or raw['optimizer_steps']!=0 or raw['optimizer_steps_start']!=0 or
        raw['policy_sha256'] is not None or raw['fault'] is not None or raw['reference_problems'] or
        raw['actual_reference_failed'] or raw['initial_audit'].get('passed') is not True or
        raw['source_session_outcome']['model_scope_qualified'] is not False or
        raw['source_session_outcome']['training_admitted'] is not False):
        raise ValueError('Zero B2 identity, initialization or scope audit failed')
    cycles=raw['control_cycles'];steps=raw['physical_substeps']
    if (type(cycles) is not int or type(steps) is not int or not 0<cycles<=14500 or
        steps!=10*cycles or len(raw['trace'])!=cycles+1 or len(raw['actions'])!=cycles or len(raw['transitions'])!=cycles):
        raise ValueError('Incomplete physical cycle/step archive')
    for action in raw['actions']:frozen_module('baseline_rollout').check_zero_log(action)
    source=raw['source_session_outcome'];out=raw['outcome']
    if source['simulation_valid']!=out['simulation_valid'] or source['physical_stopped']!=out['physical_stopped']:
        raise ValueError('Common adjudication disagrees with independent facts')
    return bool(out['simulation_valid'] is True and out['physical_stopped'] is True and
        out['guard_violations']==dict(contact=False,motion=False) and out['task_outcome'] in ('FULL_SUCCESS','TASK_FAILURE'))


def physical_case(config,point,index,run,receipt,binding):
    from scope_contract import sha
    session=None;env=None;started=time.monotonic()
    try:
        frozen_module('contract').check_runtime(binding['numerical_runtime'],check_interpreter=True)
        if not sys.flags.isolated or Path(sys.executable).resolve()!=Path(binding['executable']).resolve():
            raise PermissionError('Frozen isolated CPU interpreter required')
        from tools.learning.runtime import select_runtime,verify_runtime,active_package
        select_runtime(binding['runtime_record'],expected_digest=binding['runtime_record_sha256'])
        if digest(verify_runtime(active_package()))!=config['common']['runtime_proof_sha256']:
            raise ValueError('Frozen native runtime proof differs')
        from tools.learning.guarded_environment import LearningEnvironment,GuardCandidateConfig
        from tools.validation.run_contact_cases import ContactCase
        from tools.validation.run_clearance_preflight import archive_episode
        from tools.validation.run_v4_adapter_preflight import actual_reference_radius
        from tools.learning.outcome import classify_outcome
        from tools.model.layered_task import layered_pin_clearance_m,referee_metadata
        if referee_metadata()!=config['common']['geometry_referee']:raise ValueError('Frozen geometric referee changed')
        common=config['common'];receipt['environment_creation_attempted']=1;write(run/'receipt.json',receipt)
        env=LearningEnvironment(guard_config=GuardCandidateConfig(**common['guard_config']),model_xml=(OUT/'model.xml').read_text(encoding='utf-8'))
        receipt['environment_created']=1;write(run/'receipt.json',receipt)
        if asdict(env.config)!=common['dynamic_config'] or asdict(env.guard_config)!=common['guard_config']:
            raise ValueError('Actual physical or guard parameters drifted')
        driver=frozen_module('baseline_rollout')
        session=driver.make_session(env,common)
        snapshot=reset_once(session,ContactCase(**case_kwargs(point)),point,receipt,run,config)
        max_radius=0.;reference_checks=0

        def resources():
            if env.physical_steps>LIMITS['per_episode_native_steps']-10:
                raise RuntimeError('Native step cap before next control cycle')

        def progress(cycle,trace,actions,transitions,previous_snapshot):
            nonlocal max_radius,reference_checks
            radius=actual_reference_radius(previous_snapshot,trace[-1],session.initial)
            if radius is not None:
                reference_checks+=1;max_radius=max(max_radius,radius)
                if radius>.00012+1e-12:raise ValueError('Actual search reference radius exceeded')
            if cycle%500==0 or session.done:
                receipt.update(control_cycles=cycle,physical_substeps=env.physical_steps,
                    simulated_time_s=float(env.data.time),wall_seconds=time.monotonic()-started)
                write(run/'receipt.json',receipt)
                archive_episode(run/'episode.partial.json.gz',dict(trace=trace,actions=actions,
                    transitions=transitions,events=env.events,stop_samples=env.stop_samples))

        data=driver.drive_zero(session,snapshot,stop=lambda:(OUT/'STOP').exists(),
            cycle_limit=14500,wall_limit=1200,progress=progress,resource_check=resources)
        source=session.adjudicate()
        outcome=classify_outcome(simulation_valid=source['simulation_valid'],physical_stopped=source['physical_stopped'],
            contact_guard=bool(env.guard_facts['contact_reasons']),motion_violation=bool(env.guard_facts['motion_reasons']),
            full_success=session.task_finished and session.reason=='GEOMETRIC_SUCCESS')
        raw=dict(version='v4_training_episode_v1',scope='stratified_zero_B2_development',role='pure_B2',
            episode_id='pure_B2_'+point['id'],mode='F50',stage='pure_B2',case_id=point['id'],
            case_index=config['cases'].index(point),attempt_index=index,case=point,
            simulation_case=asdict(ContactCase(**case_kwargs(point))),seed=SEED,comparison_key=config['common_key'],
            shared_common_key=config['parent_common_key'],optimizer_steps_start=0,optimizer_steps=0,
            policy_sha256=None,policy_calls=0,observation_schema=session.observations.schema,
            initial_audit=receipt['initial_audit'],source_session_outcome=source,outcome=outcome,
            guard_facts=env.guard_facts,events=env.events,stop_samples=env.stop_samples,stop_time=session.stop_time,
            task_end_time_s=session.task_end_time,audit_end_time_s=float(env.data.time),peaks=env.peaks,
            final_session=dict(task_finished=session.task_finished,reason=session.reason,phase=env.phase),
            controller_events=session.controller.events,reference_problems=[e for e in session.controller.events
                if e['reason'] in ('SEARCH_REFERENCE_LIMIT','RESIDUAL_REFERENCE_INFEASIBLE','REFERENCE_ACTUAL_LIMIT')],
            actual_reference_failed=False,max_actual_reference_radius_m=max_radius,actual_reference_checks=reference_checks,
            control_cycles=session.cycle_id,physical_substeps=env.physical_steps,
            wall_seconds=time.monotonic()-started,fault=None,**data)
        healthy=audit_baseline(raw,config)
        task_index=min(range(len(raw['trace'])),key=lambda i:abs(raw['trace'][i]['time_s']-raw['task_end_time_s']))
        if abs(raw['trace'][task_index]['time_s']-raw['task_end_time_s'])>1e-9:raise ValueError('Task-end pose is missing')
        raw['geometry_evidence']=dict(referee_id=common['geometry_referee']['id'],
            task_end=serialize_clearance(layered_pin_clearance_m(raw['trace'][task_index])),
            audit_end=serialize_clearance(layered_pin_clearance_m(raw['trace'][-1])),
            analytic_saved_pose_only=True,new_physical_steps=0)
        raw['case_qualification']=dict(actual_initial_audit_passed=True,zero_dynamic_audit_passed=healthy,
            full_matrix_scope_qualified=False,nonzero_SAC_qualified=False,training_admitted=False)
        receipt['archive_sha256']=archive_episode(run/'episode.json.gz',raw)
        receipt.update(status='finished',healthy=healthy,outcome=outcome,control_cycles=session.cycle_id,
            physical_substeps=env.physical_steps,wall_seconds=raw['wall_seconds'])
        write(run/'receipt.json',receipt)
    except BaseException as exc:
        if env is not None:
            receipt.update(physical_substeps=int(env.physical_steps),guard_facts=env.guard_facts)
        if session is not None:receipt['control_cycles']=session.cycle_id
        receipt.update(status='error',healthy=False,error=repr(exc),wall_seconds=time.monotonic()-started)
        write(run/'receipt.json',receipt)
        partial=getattr(exc,'episode_partial',None)
        if partial is not None:
            from tools.validation.run_clearance_preflight import archive_episode
            archive_episode(run/'episode.error.json.gz',dict(**partial,error=repr(exc),events=env.events,
                guard_facts=env.guard_facts,stop_samples=env.stop_samples))
        else:
            write(run/'initial_failure.json',dict(error=repr(exc),receipt=receipt,
                actual_initial_row_repr=repr(getattr(session,'initial_trace_row',None))))
        raise
