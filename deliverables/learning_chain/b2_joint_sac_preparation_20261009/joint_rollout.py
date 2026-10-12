"""Existing physical episode loop with explicitly preserved joint pose."""
import time,math
from pathlib import Path
from dataclasses import asdict
from joint_contract import read,write,case_kwargs,check_initial_pose,SEED,canonical
from tools.learning.v4_pilot_contract import permission
from tools.validation.run_clearance_preflight import now,archive_episode

def make_session(env,mode,common):
    from tools.validation.run_v4_adapter_preflight import make_session as wiring
    from tools.learning.v4_continuation import ContinuationResidualSession
    base=wiring(env,mode,common)
    return ContinuationResidualSession(environment=env,mode=mode,controller_factory=base.controller_factory,
        finish_criteria=common['finish_criteria'],geometry_checker=base.geometry_checker)

def rollout(folder,c,s,entry,ledger,*,checkpoint=None,stop_file=None):
    import numpy as np
    from tools.learning.guarded_environment import LearningEnvironment,GuardCandidateConfig
    from tools.validation.run_contact_cases import ContactCase
    from tools.validation.run_v4_adapter_preflight import actual_reference_radius
    from tools.learning.outcome import classify_outcome
    config=read(folder/'configuration.json');common=config['common'];mode=s['mode'];stage=s['stage'];point=s['case']
    env=LearningEnvironment(guard_config=GuardCandidateConfig(**common['guard_config']),model_xml=(folder/'model.xml').read_text(encoding='utf8'))
    if asdict(env.config)!=common['dynamic_config'] or asdict(env.guard_config)!=common['guard_config']:raise ValueError('Physical configuration drift')
    session=make_session(env,mode,common)
    case=ContactCase(**case_kwargs(point))
    transitions=[];trace=[];actions=[];started=time.monotonic();before=c.updater.counts['critic'];policy=c.updater.fingerprints()['actor'];calls=0
    actual_failed=False;maxradius=0.;checks=0;raw=None
    try:
        snap=session.reset(case,seed=SEED);check_initial_pose(point,session.initial_trace_row);trace.append(session.initial_trace_row)
        while not session.done:
            if session.cycle_id>=14500 or time.monotonic()-started>1200 or (Path(stop_file) if stop_file else folder/'STOP').exists():raise RuntimeError('Registered physical bound/STOP; no retry')
            active=permission(snap.policy_observation,mode)
            if active!=snap.residual_enabled:raise ValueError('Session permission differs from schema')
            sampled=None
            if stage=='warmup':
                sampled=c.warm_action(session.cycle_id);requested=sampled if active else [0.]*4
            elif active:
                requested=c.updater.predict(np.asarray(snap.policy_observation,dtype=np.float32),deterministic=stage in ('zero','final','restore'))[0].tolist();calls+=1
            else:requested=[0.]*4
            result=session.advance_cycle(requested);trace.append(result.trace_row)
            radius=actual_reference_radius(snap,result.trace_row,session.initial)
            if radius is not None:
                checks+=1;maxradius=max(maxradius,radius)
                if radius>.00012+1e-12:
                    actual_failed=True;session._finish('REFERENCE_ACTUAL_LIMIT');session._cache=None;result.next_snapshot=session.prepare_cycle()
            log=result.action_log;actions.append(log)
            transitions.append(dict(observation=snap.policy_observation,next_observation=result.next_snapshot.policy_observation,
                action=log['experience_action'],action_active=snap.residual_enabled,next_action_active=result.next_snapshot.residual_enabled,
                reward=result.reward_terms['total'],reward_terms={**dict(terminal=0.),**result.reward_terms},dt=result.dt,
                discount=math.exp(-result.dt/10),terminated=bool(result.done),truncated=False,
                cycle_force_N=result.cycle_peaks['force_N'],cycle_torque_G_Nm=result.cycle_peaks['torque_G_Nm'],
                advance_m=result.trace_row['position_m'][2]-session.initial[2],action_log=log,trace_row=result.trace_row,
                sampling_request=sampled))
            snap=result.next_snapshot
            if session.cycle_id%500==0:
                entry.update(control_cycles=session.cycle_id,physical_substeps=env.physical_steps,simulated_time_s=float(env.data.time),policy_calls=calls)
                write(folder/'run/ledger.json',ledger)
                archive_episode(folder/'run'/(s['id']+'.partial.json.gz'),dict(trace=trace,actions=actions,transitions=transitions,
                    events=env.events,stop_samples=env.stop_samples,guard_facts=env.guard_facts))
                print(canonical(dict(id=s['id'],cycles=session.cycle_id,time_s=float(env.data.time),reason=session.reason)),flush=True)
        source=session.adjudicate()
        out=classify_outcome(simulation_valid=source['simulation_valid'],physical_stopped=source['physical_stopped'],
            contact_guard=bool(env.guard_facts['contact_reasons']),motion_violation=bool(env.guard_facts['motion_reasons']),
            full_success=session.task_finished and session.reason=='GEOMETRIC_SUCCESS')
        problems=[e for e in session.controller.events if e['reason'] in ('SEARCH_REFERENCE_LIMIT','RESIDUAL_REFERENCE_INFEASIBLE','REFERENCE_ACTUAL_LIMIT')]
        raw=dict(version='v4_training_episode_v1',scope='bounded_physical_pilot' if stage in ('warmup','online') else 'frozen_development_evaluation',
            episode_id=s['id'],mode=mode,stage=stage,case_id=point['id'],case_index=s['case_index'],case=point,simulation_case=asdict(case),seed=SEED,
            qualification_sha256=c.binding['qualification_sha256'],config_sha256=c.binding['config_sha256'],
            optimizer_steps_start=before,optimizer_steps=c.updater.counts['critic'],policy_sha256=policy,warmup_draws=c.warm_draws,
            transitions=transitions,trace=trace,actions=actions,observation_schema=session.observations.schema,
            source_session_outcome=source,outcome=out,guard_facts=env.guard_facts,events=env.events,stop_samples=env.stop_samples,
            stop_time=session.stop_time,audit_end_time_s=float(env.data.time),task_end_time_s=session.task_end_time,peaks=env.peaks,
            final_session=dict(task_finished=session.task_finished,reason=session.reason,phase=env.phase),
            controller_events=session.controller.events,reference_problems=problems,actual_reference_failed=actual_failed,
            max_actual_reference_radius_m=maxradius,actual_reference_checks=checks,policy_calls=calls,
            control_cycles=session.cycle_id,physical_substeps=env.physical_steps,wall_seconds=time.monotonic()-started,fault=None,
            checkpoint=checkpoint,comparison_key=config['common_key'])
        if before!=c.updater.counts['critic'] or policy!=c.updater.fingerprints()['actor']:raise ValueError('Optimizer advanced during physical episode')
        entry.update(status='finished',outcome=out,reason=session.reason,control_cycles=session.cycle_id,physical_substeps=env.physical_steps,
            wall_seconds=raw['wall_seconds'],policy_calls=calls,ended_at=now(),reference_problems=problems,actual_reference_failed=actual_failed)
        entry['archive_sha256']=archive_episode(folder/'run'/(s['id']+'.json.gz'),raw)
        ledger['policy_calls']+=calls;write(folder/'run/ledger.json',ledger);print(canonical(entry),flush=True)
        return raw
    except BaseException as exc:
        entry.update(status='error',error=repr(exc),control_cycles=session.cycle_id,physical_substeps=env.physical_steps,
            policy_calls=calls,wall_seconds=time.monotonic()-started,ended_at=now())
        archive_episode(folder/'run'/(s['id']+'.error.json.gz'),dict(trace=trace,actions=actions,transitions=transitions,
            events=env.events,stop_samples=env.stop_samples,guard_facts=env.guard_facts,entry=entry))
        ledger['policy_calls']+=calls;write(folder/'run/ledger.json',ledger);raise

def audit_evaluation(raw):
    from tools.validation.native313_matrix_audit import actual_stop_pass
    from tools.validation.run_contact_candidate_stop import physical_tail_pass
    from tools.validation.verify_admitted_collection import validate_outcome
    from tools.learning.v4_replay import V4Replay
    if raw['scope']!='frozen_development_evaluation' or raw['reference_problems'] or raw['actual_reference_failed'] or raw['fault'] is not None:raise ValueError('Evaluation common failure')
    stopped=bool(actual_stop_pass(raw['stop_samples'],raw['events'],raw['stop_time'],raw['audit_end_time_s'],.0002) and physical_tail_pass(raw['stop_samples'],raw['audit_end_time_s'],.0002))
    validate_outcome(raw,stopped=stopped)
    if not stopped or not raw['outcome']['simulation_valid']:raise ValueError('Unqualified evaluation physics')
    V4Replay(mode=raw['mode'],capacity=116000)._prepare(raw['transitions'])
