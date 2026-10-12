"""Frozen SAC driver; science imports only inside the admitted physical function."""
from dataclasses import asdict
from copy import deepcopy
from pathlib import Path
import math,sys,time
from sac_scope import OUT,ROOT,c,read,write,sha,digest,finite_vector,case_kwargs,check_initial_state,SEED

def failure_archive(partial,env,session,receipt,exc):
    raw=deepcopy(partial or {});raw.update(error=repr(exc),receipt=deepcopy(receipt),missing_fields=[])
    values=dict(events=getattr(env,'events',None),stop_samples=getattr(env,'stop_samples',None),
        guard_facts=getattr(env,'guard_facts',None),physical_substeps=getattr(env,'physical_steps',None),
        audit_end_time_s=getattr(getattr(env,'data',None),'time',None),stop_time=getattr(session,'stop_time',None),
        task_end_time_s=getattr(session,'task_end_time',None),control_cycles=getattr(session,'cycle_id',None),
        controller_events=getattr(getattr(session,'controller',None),'events',None))
    values['final_session']=dict(task_finished=getattr(session,'task_finished',None),reason=getattr(session,'reason',None),
        phase=getattr(env,'phase',None)) if session is not None else None
    for k,v in values.items():
        raw[k]=deepcopy(v)
        # A not-yet-defined task/stop time is normal; retain explicit None rather than claim evidence.
        if v is None and k not in ('task_end_time_s','stop_time'):raw['missing_fields'].append(k)
    return raw

def audit_command(log,requested,active):
    if log['enabled'] is not active or finite_vector(log['raw_action'],4)!=requested or finite_vector(log['experience_action'],4)!=(requested if active else [0.]*4):
        raise ValueError('Logged permission/normalized action differs')
    predicted=finite_vector(log['predicted_limited_command'],6);actual=finite_vector(log['actual_end_limited_command'],6)
    error=max(abs(a-b) for a,b in zip(predicted,actual))
    if error>1e-12:raise ValueError('Predicted and executed commands differ')
    scale=[requested[0]*5e-5,requested[1]*5e-5,0.,requested[2]*.0005,requested[3]*.0005,0.]
    if max(abs(a-b) for a,b in zip(finite_vector(log['requested_residual'],6),scale))>1e-12:
        raise ValueError('F50 residual physical scale differs')
    applied=finite_vector(log['applied_residual'],6);delta=finite_vector(log['effective_command_delta'],6)
    if not active and any(applied+delta):raise ValueError('Inactive learned correction')
    return error,int(active and any(abs(v)>1e-15 for v in applied) and any(abs(v)>1e-15 for v in delta))

def drive(session,snapshot,predict,receipt,*,permission,clock=time.monotonic,stop=lambda:False,
          resource_check=lambda:None,progress=lambda *args:None):
    started=clock();trace=[session.initial_trace_row];actions=[];transitions=[]
    for k in ('policy_calls','policy_call_attempts','nonzero_applied_command_cycles'):receipt.setdefault(k,0)
    receipt.setdefault('max_command_error',0.)
    try:
        while not session.done:
            if session.cycle_id>=14500 or clock()-started>=1200 or stop():raise RuntimeError('Registered cycle/wall/STOP bound; no retry')
            resource_check();active=permission(snapshot.policy_observation)
            if active is not snapshot.residual_enabled:raise ValueError('Session and schema permission differ')
            requested=[0.]*4
            if active:
                receipt['policy_call_attempts']+=1
                requested=finite_vector(predict(snapshot.policy_observation),4);receipt['policy_calls']+=1
                if max(abs(v) for v in requested)>1:raise ValueError('Normalized actor action outside bounds')
            result=session.advance_cycle(requested)
            trace.append(result.trace_row);actions.append(result.action_log)
            error,nonzero=audit_command(result.action_log,requested,active)
            receipt['max_command_error']=max(receipt['max_command_error'],error)
            receipt['nonzero_applied_command_cycles']+=nonzero
            if type(result.dt) not in (int,float) or not math.isfinite(result.dt) or result.dt<=0:raise ValueError('Invalid physical interval')
            transitions.append(dict(observation=snapshot.policy_observation,next_observation=result.next_snapshot.policy_observation,
                action=result.action_log['experience_action'],action_active=active,next_action_active=result.next_snapshot.residual_enabled,
                reward=result.reward_terms['total'],reward_terms={**dict(terminal=0.),**result.reward_terms},dt=result.dt,
                discount=math.exp(-result.dt/10),terminated=bool(result.done),truncated=False,
                cycle_force_N=result.cycle_peaks['force_N'],cycle_torque_G_Nm=result.cycle_peaks['torque_G_Nm'],
                advance_m=result.trace_row['position_m'][2]-session.initial[2],action_log=result.action_log,trace_row=result.trace_row,sampling_request=None))
            progress(session.cycle_id,trace,actions,transitions,snapshot);snapshot=result.next_snapshot
    except BaseException as exc:
        exc.episode_partial=dict(trace=trace,actions=actions,transitions=transitions);raise
    return dict(trace=trace,actions=actions,transitions=transitions)

def physical_case(config,unit,run,receipt,binding):
    from actor_runtime import load_state,make_actor,actor_digest
    session=None;env=None;started=time.monotonic();data=None;actor=None
    try:
        from tools.learning.runtime import select_runtime,verify_runtime,active_package
        select_runtime(binding['runtime_record'],expected_digest=binding['runtime_record_sha256'])
        common=config['common']
        if digest(verify_runtime(active_package()))!=common['runtime_proof_sha256']:raise ValueError('Frozen native runtime proof differs')
        from tools.learning.guarded_environment import LearningEnvironment,GuardCandidateConfig
        from tools.validation.run_contact_cases import ContactCase
        from tools.validation.run_clearance_preflight import archive_episode
        from tools.validation.run_v4_adapter_preflight import actual_reference_radius
        from tools.learning.v4_pilot_contract import permission
        from tools.learning.outcome import classify_outcome
        from tools.model.layered_task import layered_pin_clearance_m,referee_metadata
        if referee_metadata()!=common['geometry_referee']:raise ValueError('Geometry referee drift')
        spec=next(a for a in config['actor_specs'] if a['role']==unit['role'])
        state=load_state(spec,config,receipt,lambda:write(run/'receipt.json',receipt))
        actor=make_actor(state,spec,config,receipt,lambda:write(run/'receipt.json',receipt));del state
        receipt['actor_before']=actor_digest(actor)
        receipt['environment_creation_attempted']=1;write(run/'receipt.json',receipt)
        env=LearningEnvironment(guard_config=GuardCandidateConfig(**common['guard_config']),model_xml=(OUT/'model.xml').read_text(encoding='utf-8'))
        receipt['environment_created']=1;write(run/'receipt.json',receipt)
        if asdict(env.config)!=common['dynamic_config'] or asdict(env.guard_config)!=common['guard_config']:raise ValueError('Physical/guard config drift')
        session=c.frozen_module('baseline_rollout').make_session(env,common);point=unit['case'];case=ContactCase(**case_kwargs(point))
        receipt['reset_attempted']=1;write(run/'receipt.json',receipt);snapshot=session.reset(case,seed=SEED)
        receipt['reset_completed']=1;write(run/'receipt.json',receipt)
        receipt['initial_audit']=check_initial_state(point,session.initial_trace_row,common,env.guard_facts);write(run/'receipt.json',receipt)
        maxradius=0.;checks=0
        def resources():
            if env.physical_steps>145000-10:raise RuntimeError('Native step ceiling before next cycle')
        def progress(cycle,trace,actions,transitions,old_snapshot):
            nonlocal maxradius,checks
            radius=actual_reference_radius(old_snapshot,trace[-1],session.initial)
            if radius is not None:
                checks+=1;maxradius=max(maxradius,radius)
                if radius>.00012+1e-12:raise ValueError('Actual reference radius exceeded')
            if cycle%500==0 or session.done:
                receipt.update(control_cycles=cycle,physical_substeps=env.physical_steps,wall_seconds=time.monotonic()-started)
                write(run/'receipt.json',receipt)
                archive_episode(run/'episode.partial.json.gz',dict(trace=trace,actions=actions,transitions=transitions,events=env.events,stop_samples=env.stop_samples))
        data=drive(session,snapshot,actor.predict_action,receipt,permission=lambda o:permission(o,'F50'),
            stop=lambda:(OUT/'STOP').exists(),resource_check=resources,progress=progress)
        source=session.adjudicate();out=classify_outcome(simulation_valid=source['simulation_valid'],physical_stopped=source['physical_stopped'],
            contact_guard=bool(env.guard_facts['contact_reasons']),motion_violation=bool(env.guard_facts['motion_reasons']),
            full_success=session.task_finished and session.reason=='GEOMETRIC_SUCCESS')
        receipt['actor_after']=actor_digest(actor)
        problems=[e for e in session.controller.events if e['reason'] in ('SEARCH_REFERENCE_LIMIT','RESIDUAL_REFERENCE_INFEASIBLE','REFERENCE_ACTUAL_LIMIT')]
        raw=dict(version='v4_training_episode_v1',scope='stratified_frozen_SAC_development',role=unit['role'],mode='F50',stage=spec['stage'],
            episode_id=unit['role']+'_'+point['id'],case_id=point['id'],case_index=config['cases'].index(point),attempt_index=unit['index'],
            case=point,simulation_case=asdict(case),seed=SEED,comparison_key=config['common_key'],shared_common_key=config['parent_common_key'],
            optimizer_steps_start=spec['updates'],optimizer_steps=spec['updates'],policy_sha256=receipt['actor_before'],policy_sha256_after=receipt['actor_after'],
            observation_schema=session.observations.schema,initial_audit=receipt['initial_audit'],source_session_outcome=source,outcome=out,
            guard_facts=env.guard_facts,events=env.events,stop_samples=env.stop_samples,stop_time=session.stop_time,
            task_end_time_s=session.task_end_time,audit_end_time_s=float(env.data.time),peaks=env.peaks,
            final_session=dict(task_finished=session.task_finished,reason=session.reason,phase=env.phase),controller_events=session.controller.events,
            reference_problems=problems,actual_reference_failed=False,max_actual_reference_radius_m=maxradius,actual_reference_checks=checks,
            control_cycles=session.cycle_id,physical_substeps=env.physical_steps,policy_calls=receipt['policy_calls'],
            policy_call_attempts=receipt['policy_call_attempts'],nonzero_applied_command_cycles=receipt['nonzero_applied_command_cycles'],
            max_command_error=receipt['max_command_error'],formal_updates=0,learner_constructions=0,replay_publications=0,
            wall_seconds=time.monotonic()-started,fault=None,**data)
        if session.observations.schema!=config['schema'] or receipt['actor_before']!=receipt['actor_after'] or problems:
            raise ValueError('Schema/actor/reference audit failed')
        from sac_assess import audit_archive
        healthy=audit_archive(raw,config,unit)
        receipt['archive_sha256']=archive_episode(run/'episode.json.gz',raw)
        receipt.update(status='finished',healthy=healthy,outcome=out,control_cycles=session.cycle_id,physical_substeps=env.physical_steps,wall_seconds=raw['wall_seconds'])
        write(run/'receipt.json',receipt)
    except BaseException as exc:
        if env is not None:receipt.update(physical_substeps=int(env.physical_steps),guard_facts=env.guard_facts)
        if session is not None:receipt['control_cycles']=session.cycle_id
        receipt.update(status='error',healthy=False,error=repr(exc),wall_seconds=time.monotonic()-started)
        write(run/'receipt.json',receipt)
        partial=getattr(exc,'episode_partial',data)
        failure=failure_archive(partial,env,session,receipt,exc)
        if partial is not None or env is not None:
            from tools.validation.run_clearance_preflight import archive_episode
            archive_episode(run/'episode.error.json.gz',failure)
        else:write(run/'initial_failure.json',failure)
        raise
