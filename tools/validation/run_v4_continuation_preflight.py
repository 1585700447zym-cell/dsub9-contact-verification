"""Single development boundary pulse; no policy inference, replay or training."""
import argparse,gzip,json,math,os,time
from pathlib import Path
from dataclasses import asdict
from . import run_v4_adapter_preflight as old
from .run_clearance_preflight import write,now,archive_episode,record_error

ROOT=old.ROOT
DELIVERY=ROOT/'deliverables/paper_comparison/v4_continuation_20261006'
PRIOR=ROOT/'deliverables/paper_comparison/v4_adapter_20261004'
PLAN='docs/superpowers/plans/2026-10-06-v4-continuation-preflight.md'
SPEC=dict(id='F50_boundary_y_neg_150',method='F50',profile='single_boundary_pulse',case_id='y_neg_150',x_um=0,y_um=-150)

def input_hashes():
    paths=old.input_hashes()
    for name in [PLAN,'deliverables/paper_comparison/v4_adapter_20261004/delivery_manifest.json',
            'deliverables/task_variants/layered_referee_20261004/run/y_neg_150.json.gz']:
        paths[name]=old.sha(ROOT/name)
    return paths

def verify_inputs(folder):
    binding=old.read(folder/'preparation_binding.json')
    if set(binding)!={'configuration.json','model.xml'}:raise RuntimeError('Incomplete binding')
    for name,digest in binding.items():
        if old.sha(folder/name)!=digest:raise RuntimeError('Prepared input changed: '+name)
    config=old.read(folder/'configuration.json')
    if config['input_sha256']!=input_hashes():raise RuntimeError('Source changed')
    for name,digest in config['common']['frozen_common_source_sha256'].items():
        if old.sha(ROOT/name)!=digest:raise RuntimeError('Frozen common dependency changed: '+name)
    from tools.learning.runtime import verify_runtime,active_package
    from tools.evaluation.paper_comparison import comparison_key
    if comparison_key(verify_runtime(active_package()))!=config['common']['runtime_proof_sha256']:
        raise RuntimeError('Runtime proof changed')
    return config

def make_session(env,common):
    from tools.learning.v4_continuation import ContinuationResidualSession
    wiring=old.make_session(env,'F50',common)
    return ContinuationResidualSession(environment=env,mode='F50',controller_factory=wiring.controller_factory,
        finish_criteria=common['finish_criteria'],geometry_checker=wiring.geometry_checker)

def prepare(folder):
    if old.sha(PRIOR/'delivery_manifest.json')!='ea040c19632830c9ba30ada23683825973c507396f4f52de4de0387d1f869b73':
        raise RuntimeError('PC-02 seal changed')
    for name,rec in old.read(PRIOR/'delivery_manifest.json')['files'].items():
        if old.sha(PRIOR/name)!=rec['sha256']:raise RuntimeError('PC-02 file changed: '+name)
    config=old.prepare(folder)
    from tools.learning.guarded_environment import LearningEnvironment,GuardCandidateConfig
    env=LearningEnvironment(guard_config=GuardCandidateConfig(**config['common']['guard_config']),model_xml=(folder/'model.xml').read_text(encoding='utf8'))
    make_session(env,config['common']) # static construction; no reset or step
    config.update(cases=[SPEC],input_sha256=input_hashes(),max_episodes=1,prior_cumulative=139,cumulative_limit=140,
        script=dict(profile='one_absolute_control_time',time_s=9.146,action=[1,-1,0,0]),
        reference_filter='residual_reference_continuation_v1',scope='boundary_branch_development_no_learning')
    write(folder/'configuration.json',config)
    write(folder/'preparation_binding.json',{n:old.sha(folder/n) for n in ['configuration.json','model.xml']})
    return config

def boundary_action(snapshot,pulse_fired):
    if pulse_fired:return [0.]*4
    if abs(snapshot.time_s-9.146)<1e-9:
        if snapshot.controller_state['phase']!='SEARCH' or not snapshot.residual_enabled:
            raise RuntimeError('Registered pulse has no SEARCH permission')
        return [1.,-1.,0.,0.]
    if snapshot.time_s>9.146+1e-9:raise RuntimeError('Registered pulse time missed')
    return [0.]*4

def claim_run(folder):
    folder.mkdir(parents=True,exist_ok=False)
    ledger=dict(status='prepared',started_at=now(),episodes=[],max_new_episodes=1,prior_cumulative=139,cumulative_limit=140,
        retry_allowed=False,training_updates=0,policy_calls=0,replay_published=0,independent_tests=0)
    write(folder/'ledger.json',ledger);return ledger

def execute(folder):
    ledger=claim_run(folder/'run')
    try:
        config=verify_inputs(folder)
        if (folder/'STOP').exists():ledger.update(status='controlled_stop',stop_requested=True)
        else:run_episode(folder,ledger,config)
        verify_inputs(folder)
        if ledger['status']=='running':
            ledger['status']='complete' if ledger['episodes'][0]['verification_passed'] else 'controlled_stop'
        ledger.update(ended_at=now(),unused_closed=1-len(ledger['episodes']),inputs_unchanged=True)
        write(folder/'run/ledger.json',ledger);return ledger
    except BaseException as exc:
        ledger.update(status='error',error=repr(exc),ended_at=now(),unused_closed=1-len(ledger['episodes']))
        write(folder/'run/ledger.json',ledger);raise

def run_episode(folder,ledger,config):
    import numpy as np
    from tools.learning.guarded_environment import LearningEnvironment,GuardCandidateConfig
    from tools.validation.run_contact_cases import ContactCase
    from tools.model.layered_task import layered_pin_clearance_m
    admission=old.read(folder/'preflight_admission.json')
    if (admission.get('configuration_sha256')!=old.sha(folder/'configuration.json') or
            admission.get('allowed_scope')!='one_continuation_boundary_development_episode_only' or
            admission.get('max_new_episodes')!=1 or admission.get('training_admitted') is not False):
        raise RuntimeError('No matching bounded preflight admission')
    if (folder/'STOP').exists():ledger.update(status='controlled_stop',stop_requested=True);return
    env=LearningEnvironment(guard_config=GuardCandidateConfig(**config['common']['guard_config']),model_xml=(folder/'model.xml').read_text(encoding='utf8'))
    session=make_session(env,config['common'])
    if (folder/'STOP').exists():ledger.update(status='controlled_stop',stop_requested=True);return
    run=folder/'run';entry=dict(id=SPEC['id'],spec=SPEC,status='running',started_at=now(),control_cycles=0,physical_substeps=0)
    ledger['episodes'].append(entry);ledger['status']='running';write(run/'ledger.json',ledger)
    case=ContactCase('y_neg_150',0,-.00015,0,0,-.004,.004)
    trace=[];actions=[];transitions=[];rewards={};env_started=time.monotonic();pulse=None;followup=None
    actual_checks=0;maxradius=0.;actual_failure=False
    baseline=json.loads(gzip.decompress((old.BASE/'run/y_neg_150.json.gz').read_bytes()))['trace']
    try:
        snapshot=session.reset(case);trace.append(session.initial_trace_row)
        while not session.done:
            if session.cycle_id>=14500 or time.monotonic()-env_started>1200 or (folder/'STOP').exists():
                raise RuntimeError('Bounded run interrupted; no retry')
            vector=np.asarray(snapshot.policy_observation)
            assert vector.shape==(137,) and np.isfinite(vector).all()
            expected=session.stage_permission(snapshot.controller_state['phase'],env.phase=='RUNNING' and session.reason is None and not session.guard_latched and not session.done)
            assert snapshot.residual_enabled==expected and bool(snapshot.policy_raw['action_active'][0])==expected
            assert snapshot.policy_raw['previous_limited_command']==env.command.tolist()
            requested=boundary_action(snapshot,pulse is not None)
            firing=any(requested)
            if firing:
                if trace!=baseline[:len(trace)]:raise RuntimeError('Pre-pulse physical trajectory differs')
                prefix_samples=len(trace)
            result=session.advance_cycle(requested);trace.append(result.trace_row)
            radius=old.actual_reference_radius(snapshot,result.trace_row,session.initial)
            if radius is not None:
                actual_checks+=1;maxradius=max(maxradius,radius)
                if radius>.00012+1e-12:
                    actual_failure=True;session._finish('REFERENCE_ACTUAL_LIMIT');session._cache=None
                    result.next_snapshot=session.prepare_cycle()
            log=result.action_log;log.update(cycle=session.cycle_id,command_time_s=snapshot.time_s,policy_phase=snapshot.controller_state['phase'])
            assert log['experience_action']==(requested if log['enabled'] else [0.]*4)
            if firing:pulse=dict(command_time_s=snapshot.time_s,cycle=session.cycle_id,prefix_samples=prefix_samples,log=log)
            elif pulse is not None and followup is None:
                followup=dict(cycle=session.cycle_id,policy_phase=snapshot.controller_state['phase'],reason=session.reason,
                    log=log,trace_row=result.trace_row)
            actions.append(log)
            for k,v in result.reward_terms.items():rewards[k]=rewards.get(k,0.)+v
            transitions.append(dict(observation=snapshot.policy_observation,next_observation=result.next_snapshot.policy_observation,
                action=log['experience_action'],action_active=snapshot.residual_enabled,next_action_active=result.next_snapshot.residual_enabled,
                reward=result.reward_terms['total'],reward_terms=result.reward_terms,dt=result.dt,discount=math.exp(-result.dt/10),
                terminated=bool(result.done),truncated=False,cycle_force_N=result.cycle_peaks['force_N'],
                cycle_torque_G_Nm=result.cycle_peaks['torque_G_Nm'],advance_m=result.trace_row['position_m'][2]-session.initial[2]))
            snapshot=result.next_snapshot
            if session.cycle_id%500==0:
                entry.update(control_cycles=session.cycle_id,physical_substeps=env.physical_steps,simulated_time_s=float(env.data.time))
                write(run/'ledger.json',ledger)
                archive_episode(run/(SPEC['id']+'.partial.json.gz'),dict(trace=trace,actions=actions,pulse=pulse,followup=followup,
                    transitions=transitions,events=env.events,stop_samples=env.stop_samples,guard_facts=env.guard_facts))
                print(json.dumps(dict(cycles=session.cycle_id,time_s=float(env.data.time),pulse_fired=pulse is not None)),flush=True)
        outcome=session.adjudicate();final=env.observe()
        reference_reasons={'SEARCH_REFERENCE_LIMIT','RESIDUAL_REFERENCE_INFEASIBLE','REFERENCE_ACTUAL_LIMIT'}
        problems=[e for e in session.controller.events if e['reason'] in reference_reasons]
        pulse_pass=bool(pulse and pulse['log']['continuation_filtered'] and pulse['log']['next_zero_reference_feasible']
            and pulse['log']['reference_filter_fraction']<1 and followup and followup['policy_phase']=='SEARCH')
        verification=bool(pulse_pass and not actual_failure and not problems and outcome['simulation_valid']
            and outcome['physical_stopped'] and not any(outcome['guard_violations'].values()))
        entry.update(status='finished',ended_at=now(),outcome=outcome,reason=session.reason,verification_passed=verification,
            pulse_pass=pulse_pass,pulse=pulse,followup=followup,reference_problems=problems,
            actual_reference_checks=actual_checks,max_actual_reference_radius_m=maxradius,actual_reference_failed=actual_failure,
            filter_cycles=sum(l['reference_filter_fraction']<1 for l in actions),
            continuation_filter_cycles=sum(l['continuation_filtered'] for l in actions),
            reward_totals=rewards,control_cycles=session.cycle_id,physical_substeps=env.physical_steps,wall_seconds=time.monotonic()-env_started,
            stop_time=session.stop_time,task_end_time=session.task_end_time,end_time=float(env.data.time),peaks=env.peaks,
            xy_um=float(np.linalg.norm(final['position_m'][:2]))*1e6,z_um=final['position_m'][2]*1e6,
            pin_clearance_um=layered_pin_clearance_m(final)*1e6)
        data=dict(status='finished',case=asdict(case),trace=trace,actions=actions,transitions=transitions,
            observation_schema=session.observations.schema,events=env.events,stop_samples=env.stop_samples,
            guard_facts=env.guard_facts,controller_events=session.controller.events,summary=entry)
        entry['archive_sha256']=archive_episode(run/(SPEC['id']+'.json.gz'),data)
        write(run/'ledger.json',ledger);print(json.dumps({k:v for k,v in entry.items() if k not in ('pulse','followup')},ensure_ascii=False),flush=True)
    except BaseException as exc:
        record_error(run,ledger,entry,exc,case,trace,env,session)
        archive_episode(run/(SPEC['id']+'.adapter_error.json.gz'),dict(actions=actions,transitions=transitions,pulse=pulse,followup=followup))
        raise

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--prepare',action='store_true');parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    if args.prepare==args.execute:parser.error('Choose one operation')
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime();os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'tmp/matplotlib_v4_continuation'))
    if args.prepare:
        if (DELIVERY/'configuration.json').exists():raise FileExistsError('Prepared already')
        prepare(DELIVERY);print('Prepared; dynamic=0 training=0')
    else:
        result=execute(DELIVERY)
        print(json.dumps({k:v for k,v in result.items() if k!='episodes'},ensure_ascii=False))

if __name__=='__main__':main()
