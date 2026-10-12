"""One-claim v4 adapter/B1 qualification: at most nine rollouts, no learning."""
import argparse,gzip,hashlib,json,math,os,time
from dataclasses import asdict
from pathlib import Path
from tools.validation.run_clearance_preflight import write,now,archive_episode,record_error

ROOT=Path(__file__).resolve().parents[2]
DELIVERY=ROOT/'deliverables/paper_comparison/v4_adapter_20261004'
BASE=ROOT/'deliverables/task_variants/layered_referee_20261004'
PROTOCOL=ROOT/'deliverables/paper_comparison/protocol_v4_20261004'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))

def case_specs():
    return [dict(id=method+'_'+profile+'_'+name,method=method,profile=profile,case_id=name,x_um=x,y_um=y)
        for method,profile,name,x,y in [('F50','zero','y_neg_150',0,-150),('F50','zero','y_pos_150',0,150),
            ('F50','pulse','y_pos_150',0,150),('S50','pulse','y_pos_150',0,150)]+
            [('B1','zero',c['id'],c['x_um'],c['y_um']) for c in read(BASE/'configuration.json')['cases']]]

def next_case(entries):
    specs=case_specs()
    if len(entries)>9 or any(e['id']!=specs[i]['id'] for i,e in enumerate(entries)):raise RuntimeError('Invalid attempt sequence')
    for i,e in enumerate(entries):
        if e['status']!='finished':raise RuntimeError('Unfinished attempt cannot be retried')
        o=e['outcome']
        if not e['verification_passed'] or not o['simulation_valid'] or not o['physical_stopped']:return None
        allowed=('FULL_SUCCESS','TASK_FAILURE','CONTACT_GUARD','MOTION_VIOLATION') if specs[i]['method']=='B1' else ('FULL_SUCCESS','TASK_FAILURE')
        if o['task_outcome'] not in allowed:return None
    return specs[len(entries)] if len(entries)<9 else None

def claim_run(folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    ledger=dict(status='prepared',started_at=now(),episodes=[],max_new_episodes=9,prior_cumulative=130,cumulative_limit=139,
                training_updates=0,policy_calls=0,independent_tests=0,retry_allowed=False)
    write(folder/'ledger.json',ledger);return ledger

def input_hashes():
    paths=list((ROOT/'tools').rglob('*.py'))+list((ROOT/'models').rglob('*.xml'))+list((ROOT/'assets').rglob('*.stl'))
    paths += [ROOT/'docs/superpowers/plans/2026-10-04-v4-residual-adapter.md',PROTOCOL/'protocol.json',PROTOCOL/'delivery_manifest.json',
              BASE/'configuration.json',BASE/'run/ledger.json']
    paths += [ROOT/name for name in read(PROTOCOL/'protocol.json')['common']['frozen_common_source_sha256']]
    return {p.relative_to(ROOT).as_posix():sha(p) for p in paths}

def verify_inputs(folder):
    binding=read(folder/'preparation_binding.json')
    if set(binding)!={'configuration.json','model.xml'}:raise RuntimeError('Incomplete preparation binding')
    for name,digest in binding.items():
        if sha(folder/name)!=digest:raise RuntimeError('Prepared file changed: '+name)
    config=read(folder/'configuration.json')
    if config['input_sha256']!=input_hashes():raise RuntimeError('Execution source changed')
    for name,digest in config['common']['frozen_common_source_sha256'].items():
        if sha(ROOT/name)!=digest:raise RuntimeError('Frozen common input changed: '+name)
    from tools.learning.runtime import verify_runtime,active_package
    from tools.evaluation.paper_comparison import comparison_key
    if comparison_key(verify_runtime(active_package()))!=config['common']['runtime_proof_sha256']:
        raise RuntimeError('Execution runtime differs from frozen proof')
    return config

def make_session(env,method,common):
    from tools.learning.v4_session import V4ResidualSession
    from tools.learning.guarded_session import CandidateEpisodeSession
    from tools.model.layered_task import functional_finish,layered_pin_fit,referee_metadata
    from tools.control.v4_b1 import V4FixedAdmittance
    from tools.control.reference_search import ReferenceSearchRecovery,DriveSearchConfig
    from tools.control.search_recovery import SearchConfig
    from tools.control.risk_search import RotationRiskConfig
    from tools.control.load_search import SearchLoadConfig
    if asdict(env.config)!=common['dynamic_config'] or asdict(env.guard_config)!=common['guard_config']:
        raise ValueError('Environment differs from frozen common task')
    if referee_metadata()!=common['geometry_referee']:raise ValueError('Referee version differs')
    class B1Session(CandidateEpisodeSession):
        def completion_ready(self,row):return functional_finish(row,self.finish_criteria)
    if method=='B1':
        return B1Session(environment=env,controller_factory=V4FixedAdmittance,
                         finish_criteria=common['finish_criteria'],geometry_checker=layered_pin_fit)
    return V4ResidualSession(environment=env,mode=method,controller_factory=lambda:ReferenceSearchRecovery(
        SearchConfig(**common['b2_config']),RotationRiskConfig(**common['rotation_risk']),
        SearchLoadConfig(**common['search_load']),DriveSearchConfig(**common['drive_limits'])),
        finish_criteria=common['finish_criteria'],geometry_checker=layered_pin_fit)

def prepare(folder):
    from tools.model.clearance_task import build_task_xml
    from tools.learning.guarded_environment import LearningEnvironment,GuardCandidateConfig
    from tools.learning.runtime import verify_runtime,active_package
    from tools.evaluation.paper_comparison import comparison_key
    protocol=read(PROTOCOL/'protocol.json');common=protocol['common']
    if sha(PROTOCOL/'delivery_manifest.json')!='ed7d406236741eeefdb0b78983bb531d49c35e0f6bb901930418bd86e2dd7bd6':raise RuntimeError('PC-01 seal changed')
    if protocol['comparison_key']!=comparison_key(common):raise RuntimeError('Invalid common fingerprint')
    for name,digest in common['frozen_common_source_sha256'].items():
        if sha(ROOT/name)!=digest:raise RuntimeError('Frozen common input changed: '+name)
    if sha(ROOT/'tools/evaluation/paper_comparison.py')!=common['evaluator_source_sha256']:raise RuntimeError('Evaluator changed')
    xml=build_task_xml();assert hashlib.sha256(xml.encode()).hexdigest()==common['canonical_model_sha256']
    runtime=verify_runtime(active_package())
    assert comparison_key(runtime)==common['runtime_proof_sha256']
    env=LearningEnvironment(guard_config=GuardCandidateConfig(**common['guard_config']),model_xml=xml)
    for method in ('B1','F50','S50'):make_session(env,method,common)  # static wiring; no reset/step
    (folder/'model.xml').write_text(xml,encoding='utf-8',newline='\n')
    config=dict(common=common,common_key=protocol['comparison_key'],cases=case_specs(),input_sha256=input_hashes(),
        runtime_proof=runtime,reference_filter='limited_velocity_segment_v1',observation_version='residual_reference_whitelist_v4',
        script=dict(profile='phase_start_20_to_120ms',action=[.1,-.1,.1,-.1]),max_episodes=9,max_cycles=14500,
        per_episode_wall_s=1200,training_admitted=False,training_updates=0,policy_calls=0)
    write(folder/'configuration.json',config)
    write(folder/'preparation_binding.json',{n:sha(folder/n) for n in ['configuration.json','model.xml']})
    return config

def script_action(snapshot,profile):
    phase=snapshot.controller_state['phase'];elapsed=snapshot.time_s-snapshot.controller_state['phase_start']
    return [.1,-.1,.1,-.1] if profile=='pulse' and phase in ('INSERT','SEARCH') and .02<=elapsed<.12 else [0.]*4

def close_run(folder,ledger):
    ledger['unused_closed']=9-len(ledger['episodes']);ledger['ended_at']=now()
    try:verify_inputs(folder)
    except Exception as exc:
        ledger.update(status='input_changed',inputs_unchanged=False,error=repr(exc));write(folder/'run/ledger.json',ledger);raise
    ledger.update(status='complete' if len(ledger['episodes'])==9 else 'controlled_stop',inputs_unchanged=True)
    write(folder/'run/ledger.json',ledger);return ledger

def actual_reference_radius(snapshot,row,initial):
    if (snapshot.controller_state['phase']!='SEARCH' or not snapshot.residual_enabled or row['phase']!='RUNNING'):
        return None
    import numpy as np
    origin=np.asarray(initial)[:2]+np.asarray(snapshot.controller_state['search_origin'])[:2]
    radius=float(np.linalg.norm(np.asarray(row['reference_qpos'])[:2]-origin))
    if not math.isfinite(radius):raise ValueError('Nonfinite actual reference')
    return radius

def execute(folder):
    ledger=claim_run(folder/'run')
    try:return _execute_claimed(folder,ledger)
    except BaseException as exc:
        if ledger.get('status')!='input_changed':ledger['status']='error'
        ledger.update(error=repr(exc),ended_at=now(),unused_closed=9-len(ledger['episodes']))
        write(folder/'run/ledger.json',ledger)
        raise

def _execute_claimed(folder,ledger):
    run=folder/'run'
    try:config=verify_inputs(folder)
    except Exception as exc:
        ledger.update(status='input_changed',unused_closed=9,ended_at=now(),error=repr(exc));write(run/'ledger.json',ledger);raise
    import numpy as np
    from tools.learning.guarded_environment import LearningEnvironment,GuardCandidateConfig
    from tools.validation.run_contact_cases import ContactCase
    from tools.model.layered_task import layered_pin_clearance_m
    ledger['status']='running';write(run/'ledger.json',ledger)
    while True:
        if (folder/'STOP').exists():
            ledger['stop_requested']=True;break
        spec=next_case(ledger['episodes'])
        if spec is None:break
        entry=dict(id=spec['id'],spec=spec,status='running',started_at=now(),control_cycles=0,physical_substeps=0)
        env=session=None;trace=[];actions=[];observations=[];rewards={};start=time.monotonic()
        actual_reference_checks=0;actual_reference_failed=False;max_actual_reference_radius=0.
        case=ContactCase(spec['case_id'],spec['x_um']*1e-6,spec['y_um']*1e-6,0.,0.,-.004,.004)
        try:
            if (folder/'STOP').exists():ledger['stop_requested']=True;break
            env=LearningEnvironment(guard_config=GuardCandidateConfig(**config['common']['guard_config']),model_xml=(folder/'model.xml').read_text(encoding='utf-8'))
            session=make_session(env,spec['method'],config['common'])
            if (folder/'STOP').exists():ledger['stop_requested']=True;break
            ledger['episodes'].append(entry);write(run/'ledger.json',ledger)
            snapshot=session.reset(case)
            trace.append(session.initial_trace_row);width=None;last_phase=None
            while not session.done:
                if session.cycle_id>=14500 or time.monotonic()-start>1200 or (folder/'STOP').exists():raise RuntimeError('Bounded preflight interrupted; no retry')
                phase=snapshot.controller_state['phase']
                if spec['method']!='B1':
                    vector=snapshot.policy_observation
                    if width is None:width=len(vector)
                    assert len(vector)==width and np.isfinite(vector).all()
                    expected=session.stage_permission(phase,env.phase=='RUNNING' and session.reason is None and not session.guard_latched and not session.done)
                    assert snapshot.residual_enabled==expected and bool(snapshot.policy_raw['action_active'][0])==expected
                    assert snapshot.policy_raw['previous_limited_command']==env.command.tolist()
                    if phase!=last_phase or session.cycle_id%500==0:
                        observations.append(dict(cycle=session.cycle_id,phase=phase,vector=vector,raw=snapshot.policy_raw))
                last_phase=phase
                requested=script_action(snapshot,spec['profile']);result=session.advance_cycle(requested)
                trace.append(result.trace_row)
                actual_radius=actual_reference_radius(snapshot,result.trace_row,session.initial)
                if actual_radius is not None:
                    actual_reference_checks+=1;max_actual_reference_radius=max(max_actual_reference_radius,actual_radius)
                    if actual_radius>config['common']['b2_config']['spiral_radius_m']+1e-12:
                        actual_reference_failed=True
                        session._finish('REFERENCE_ACTUAL_LIMIT')
                        session._cache=None
                        result.next_snapshot=session.prepare_cycle()
                if spec['method']!='B1':
                    log=result.action_log;log.update(cycle=session.cycle_id,command_time_s=snapshot.time_s,policy_phase=phase)
                    assert log['experience_action']==(requested if log['enabled'] else [0.]*4)
                    if log.get('reference_checked'):
                        assert np.linalg.norm(log['predicted_reference_xy_m'])<=config['common']['b2_config']['spiral_radius_m']+1e-12
                    actions.append(log)
                    for k,v in result.reward_terms.items():rewards[k]=rewards.get(k,0.)+v
                snapshot=result.next_snapshot
                if session.cycle_id%500==0:
                    entry.update(control_cycles=session.cycle_id,physical_substeps=env.physical_steps,simulated_time_s=float(env.data.time))
                    write(run/'ledger.json',ledger)
                    archive_episode(run/(spec['id']+'.partial.json.gz'),dict(status='partial',trace=trace,actions=actions,events=env.events,stop_samples=env.stop_samples,guard_facts=env.guard_facts))
                    print(json.dumps(dict(id=spec['id'],cycles=session.cycle_id,time_s=float(env.data.time))),flush=True)
            outcome=session.adjudicate();equivalence=None;verification=not actual_reference_failed
            if spec['method']=='F50' and spec['profile']=='zero':
                old_entry=next(e for e in read(BASE/'run/ledger.json')['episodes'] if e['id']==spec['case_id'])
                oldpath=BASE/'run'/(spec['case_id']+'.json.gz');assert sha(oldpath)==old_entry['archive_sha256']
                old=json.loads(gzip.decompress(oldpath.read_bytes()))
                equivalence=dict(trace_equal=trace==old['trace'],events_equal=env.events==old['events'],
                    controller_events_equal=session.controller.events==old['controller_events'],outcome_equal=outcome==old_entry['outcome'],
                    samples=len(trace),baseline_samples=len(old['trace']))
                verification=verification and all(equivalence[k] for k in ['trace_equal','events_equal','controller_events_equal','outcome_equal'])
            channel_effects=[sum(abs(log['effective_command_delta'][i])>1e-15 for log in actions) for i in (0,1,3,4)]
            if spec['profile']=='pulse':verification=verification and all(channel_effects) and not any('reference_failure' in log for log in actions)
            final=env.observe()
            entry.update(status='finished',ended_at=now(),outcome=outcome,reason=session.reason,verification_passed=bool(verification),
                equivalence=equivalence,nonzero_effect_cycles_by_channel=channel_effects,observation_width=width,
                actual_reference_checks=actual_reference_checks,actual_reference_failed=actual_reference_failed,
                max_actual_reference_radius_m=max_actual_reference_radius,
                filter_cycles=sum(a.get('reference_filter_fraction',1)<1 for a in actions),reward_totals=rewards,
                control_cycles=session.cycle_id,physical_substeps=env.physical_steps,wall_seconds=time.monotonic()-start,
                stop_time=session.stop_time,task_end_time=session.task_end_time,end_time=float(env.data.time),peaks=env.peaks,
                xy_um=float(np.linalg.norm(final['position_m'][:2]))*1e6,z_um=final['position_m'][2]*1e6,
                pin_clearance_um=layered_pin_clearance_m(final)*1e6)
            data=dict(status='finished',case=asdict(case),trace=trace,actions=actions,observations=observations,
                observation_schema=[] if spec['method']=='B1' else session.observations.schema,
                events=env.events,stop_samples=env.stop_samples,guard_facts=env.guard_facts,controller_events=session.controller.events,summary=entry)
            entry['archive_sha256']=archive_episode(run/(spec['id']+'.json.gz'),data)
            write(run/'ledger.json',ledger);print(json.dumps(entry,ensure_ascii=False),flush=True)
        except BaseException as exc:
            record_error(run,ledger,entry,exc,case,trace,env,session)
            # Preserve adapter-specific diagnostics even if standard archive fails.
            archive_episode(run/(spec['id']+'.adapter_error.json.gz'),dict(actions=actions,observations=observations,rewards=rewards))
            raise
    return close_run(folder,ledger)

def main():
    p=argparse.ArgumentParser();p.add_argument('--prepare',action='store_true');p.add_argument('--execute',action='store_true');args=p.parse_args()
    if args.prepare==args.execute:p.error('Choose one operation')
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime();os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'tmp/matplotlib_v4_adapter'))
    if args.prepare:
        if (DELIVERY/'configuration.json').exists():raise FileExistsError('Prepared already')
        prepare(DELIVERY);print('Prepared; dynamics=0, training=0')
    else:print(json.dumps(execute(DELIVERY),ensure_ascii=False))

if __name__=='__main__':main()
