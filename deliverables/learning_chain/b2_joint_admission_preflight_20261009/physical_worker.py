"""Deferred physical backend. Imported only after grant, claim, live parent and job GO."""
from copy import deepcopy
from dataclasses import asdict
import gzip
import math
import os
from pathlib import Path
import time
import uuid
from scope_contract import ROOT, proposal, read, canonical, case_kwargs, profile_action, attempt_specs
from execution_contract import check_initial_pose, write


def serial(value):
    if isinstance(value,float) and not math.isfinite(value):return {'nonfinite':str(value)}
    if isinstance(value,dict):return {k:serial(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)):return [serial(v) for v in value]
    if hasattr(value,'tolist'):return serial(value.tolist())
    return value


def archive(path,raw):
    path=Path(path);temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    data=gzip.compress(canonical(serial(raw)).encode('utf-8'),compresslevel=1,mtime=0)
    with temp.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
    os.replace(temp,path)


def make_physical(kw,kind,common,costs):
    from tools.learning.guarded_environment import LearningEnvironment,GuardCandidateConfig
    from tools.validation.run_contact_cases import ContactCase
    env=LearningEnvironment(guard_config=GuardCandidateConfig(**common['guard_config']),
        model_xml=(ROOT/proposal()['parent']['model']).read_text(encoding='utf-8'))
    case=ContactCase(**kw)
    parameters=dict(dynamic_config=asdict(env.config),guard_config=asdict(env.guard_config))
    if parameters!=dict(dynamic_config=common['dynamic_config'],guard_config=common['guard_config']):
        raise ValueError('Physical configuration differs from parent')
    if kind=='static':return env,None,case,parameters
    from tools.validation.run_v4_adapter_preflight import make_session as wiring
    from tools.learning.v4_continuation import ContinuationResidualSession
    base=wiring(env,'F50',common)
    from recovery_fixture import session_type
    session=session_type(ContinuationResidualSession)(environment=env,mode='F50',controller_factory=base.controller_factory,
        finish_criteria=common['finish_criteria'],geometry_checker=base.geometry_checker)
    return env,session,case,parameters


def run_case(request,binding,*,factory=None):
    spec=request['spec']
    if spec not in attempt_specs(proposal()):raise ValueError('Unregistered attempt')
    folder=Path(request['output']);base=folder/spec['id'];started=time.monotonic()
    common=read(ROOT/proposal()['parent']['configuration'])['common']
    costs=dict(case_environment_instances_attempted=0,case_environment_instances_completed=0,reset_attempts=0,
        resets_completed=0,native_step_calls=0,learner_constructions=0,tensor_reads=0,network_forwards=0,
        optimizer_updates=0,replay_publications=0)
    raw=dict(version='b2_joint_preflight_raw_v1',spec=spec,binding_sha256=request['binding_sha256'],
        simulation_case=case_kwargs(spec['case']),initial=None,trace=[],cycles=[],events=[],stop_samples=[],
        costs=costs,physical_substeps=0,control_cycles=0,outcome=None,fault=None,parameters=None)
    env=session=None;native=None;original_step=None;continuation=None;original_compose=None
    observation_class=None;original_capture=None;observations={}
    def checkpoint(suffix):
        if env is not None:
            raw.update(physical_substeps=env.physical_steps,events=deepcopy(env.events),
                stop_samples=deepcopy(env.stop_samples),guard_facts=deepcopy(env.guard_facts),peaks=deepcopy(env.peaks))
        if session is not None:
            raw.update(control_cycles=getattr(session,'cycle_id',0),controller_events=deepcopy(getattr(session,'controller',None).events)
                if hasattr(session,'controller') else [])
        raw['fixture_events']=deepcopy(session.fixture.events) if session is not None and getattr(session,'fixture',None) else []
        raw['recovery_transitions']=deepcopy(session.fixture.transitions) if session is not None and getattr(session,'fixture',None) else []
        raw['wall_seconds']=time.monotonic()-started
        raw['observations']=[observations[k] for k in sorted(observations)]
        archive(base.with_suffix(suffix),raw)
    def boundary():
        if (folder/'STOP').exists() or time.time()>=request['deadline']:
            raise TimeoutError('Supervised STOP/deadline; physical stop is not inferred')
    try:
        boundary()
        if factory is None:
            from tools.learning.runtime import select_runtime,verify_runtime,active_package
            runtime=ROOT/'deliverables/learning_chain/b2_repaired_cycle_v2_20260928/runtime.json'
            select_runtime(runtime,expected_digest=binding['files'][str(runtime)])
            proof=verify_runtime(active_package());raw['runtime_proof']=proof
            from tools.evaluation.paper_comparison import comparison_key
            if comparison_key(proof)!=common['runtime_proof_sha256']:raise ValueError('Runtime proof differs')
            import mujoco as native
            original_step=native.mj_step
            def step(*args,**kwargs):
                boundary()
                if spec['kind']=='static' or costs['native_step_calls']>=145000:
                    raise TimeoutError('Native step ceiling')
                costs['native_step_calls']+=1
                return original_step(*args,**kwargs)
            native.mj_step=step
            factory=make_physical
        costs['case_environment_instances_attempted']=1
        write(base.with_suffix('.costs.json'),costs)
        env,session,case,parameters=factory(case_kwargs(spec['case']),spec['kind'],common,costs)
        costs['case_environment_instances_completed']=1;raw['parameters']=parameters
        boundary();costs['reset_attempts']=1;write(base.with_suffix('.costs.json'),costs)
        if spec['kind']=='static':
            row=env.reset(case,allow_initial_contact=False)
            raw['initial']=deepcopy(row);costs['resets_completed']=1
            check_initial_pose(spec['case'],row)
            if env.physical_steps!=0 or float(env.data.time)!=0:raise ValueError('Static initialization integrated')
            if row['contact_count'] or row['penetration_m']>1e-9 or not env.guard_facts['simulation_valid']:
                raise ValueError('Static case invalid/contact')
            raw['outcome']=dict(simulation_valid=True,initialization_valid=True)
        else:
            # Capture actual composition inputs *inside* the inherited command
            # function, including reference-release/STOP rebases. Return values
            # and all original controller decisions remain unchanged.
            import tools.learning.v4_continuation as continuation
            original_compose=continuation.compose_continuation_command;contexts=[]
            def capture(base_command,action,**kwargs):
                saved=deepcopy(kwargs)
                if saved.get('search_config') is not None:saved['search_config']=asdict(saved['search_config'])
                contexts.append(serial(dict(saved,base=base_command,action=action)))
                return original_compose(base_command,action,**kwargs)
            continuation.compose_continuation_command=capture
            from tools.learning.v4_observation import V4ObservationBuilder
            observation_class=V4ObservationBuilder;original_capture=observation_class.capture
            def capture_observation(builder,snapshot,context,*,refresh=False):
                inputs=dict(snapshot=asdict(snapshot),context=deepcopy(context))
                answer=original_capture(builder,snapshot,context,refresh=refresh)
                observations[snapshot.cycle_id]=inputs
                raw['observation_schema']=deepcopy(builder.schema)
                return answer
            observation_class.capture=capture_observation
            from recovery_fixture import RecoveryFixture
            session.fixture=RecoveryFixture() if spec['profile']=='R_RECOVERY' else None
            snap=session.reset(case,seed=20261009);costs['resets_completed']=1
            raw['initial']=deepcopy(env.observe());check_initial_pose(spec['case'],raw['initial'])
            raw['trace'].append(deepcopy(session.initial_trace_row))
            while not session.done:
                boundary()
                if session.cycle_id>=14500 or env.physical_steps>=145000:raise TimeoutError('Cycle/step ceiling includes tail')
                before=asdict(snap);phase=snap.controller_state['phase']
                elapsed=snap.time_s-snap.controller_state['phase_start']
                requested=session.fixture.action(snap,session.recovery_state) if session.fixture else profile_action(spec['profile'],snap.cycle_id,snap.residual_enabled)
                contexts.clear();result=session.advance_cycle(requested)
                raw['trace'].append(deepcopy(result.trace_row))
                raw['cycles'].append(dict(before=before,after=asdict(result.next_snapshot),requested=requested,
                    composition=deepcopy(contexts),result=asdict(result)))
                snap=result.next_snapshot
                if session.cycle_id%500==0:checkpoint('.partial.json.gz')
            raw.update(outcome=session.adjudicate(),stop_time=session.stop_time,audit_end_time_s=float(env.data.time),
                task_end_time_s=session.task_end_time,final_session=dict(task_finished=session.task_finished,reason=session.reason,phase=env.phase))
        boundary();checkpoint('.json.gz');write(base.with_suffix('.costs.json'),costs)
        return raw
    except BaseException as exc:
        raw['fault']=repr(exc)
        checkpoint('.error.json.gz');write(base.with_suffix('.costs.json'),costs)
        raise
    finally:
        if original_step is not None:native.mj_step=original_step
        if original_compose is not None:continuation.compose_continuation_command=original_compose
        if original_capture is not None:observation_class.capture=original_capture
