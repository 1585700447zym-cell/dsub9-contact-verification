"""Fixed PC-09 deployment probe. No optimization or new experience publication."""
import argparse,gzip,hashlib,json,os,sys,time,math
from pathlib import Path
from types import SimpleNamespace
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];sys.path.insert(0,str(ROOT))
import numpy as np
PRIOR=ROOT/'deliverables/paper_comparison/v4_learning_requalification_20261006'
PC07=ROOT/'deliverables/paper_comparison/frozen_comparison_20261007'
PC08=ROOT/'deliverables/paper_comparison/residual_effect_diagnosis_20261007'
PRIOR_PIN='5a6da84a149bc1e5315eb308c65a86e20375bdb0788e09a2058a27ee638cc74f'
PLAN='docs/superpowers/plans/2026-10-07-contact-gate-probe.md'
SEALS={PRIOR:'fd98d247484e919c3c4e099d03575b1d4d40e977a5da939efc088759c84b9ed5',
       PC07:'8c64d623247c31e217f71e90cbb473c3d21a05c49360f10872dab4eddd36596c',
       PC08:'1500e169da44e364c33dc01e84b30538b3de2abedb37c9486055d6fe4687a76f'}

def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def canonical(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def write(p,v):
    from tools.validation.run_clearance_preflight import write as atomic_write
    atomic_write(p,v)
def now():
    from tools.validation.run_clearance_preflight import now as clock
    return clock()

def attempt_specs(common):
    points={p['id']:p for p in common['cases']};out=[]
    for i,name in enumerate(('aligned','y_neg_150')):
        for profile in ('B2','F50','F12.5','G50'):
            out.append(dict(id='probe_'+profile.replace('.','p')+'_'+name,profile=profile,case=points[name],case_index=i,stage='deployment'))
    return out

def next_spec(ledger,specs):
    if ledger['status'] in ('error','controlled_stop','complete'):return None
    entries=ledger['episodes'];ids=[e['id'] for e in entries]
    if len(specs)!=8 or len(set(ids))!=len(ids) or ids!=[s['id'] for s in specs[:len(ids)]] or len(ids)>8:
        raise RuntimeError('Unknown/duplicate/out-of-order/excess attempt')
    if any(e['status']!='finished' for e in entries):raise RuntimeError('Unfinished attempt cannot be retried')
    return specs[len(ids)] if len(ids)<8 else None

def reconcile_calls(ledger):
    calls=attempts=0
    for e in ledger['episodes']:
        c=e.get('policy_calls',0);a=e.get('policy_call_attempts',0)
        if type(c) is not int or type(a) is not int or c<0 or a<c or (e['profile']=='B2' and (c or a)):
            raise ValueError('Invalid actual network cost')
        calls+=c;attempts+=a
    ledger.update(policy_calls=calls,policy_call_attempts=attempts,network_policy_calls=calls)

def verify_frozen_state(before,after):
    from tools.learning.sac_checkpoint import _same
    if not _same(before,after):raise ValueError('Full frozen model/optimizer/RNG state changed')
    return True

class ZeroUpdater:
    def __init__(self):self.counts=dict(critic=0,actor=0,target=0,temperature=0)
    def fingerprints(self):return dict(actor=hashlib.sha256(b'pc09-zero-without-network').hexdigest())
    def _snapshot(self):return dict(counts=dict(self.counts),provider='zero_without_network')

def verify_sources(config,*,full=False):
    from tools.validation.run_v4_learning_pilot import PilotAdmission
    original=read(PRIOR/'configuration.json')
    if config['common']!=original['common'] or config['common_key']!=original['common_key'] or config['attempts']!=attempt_specs(original['common']):
        raise ValueError('Common/task matrix changed')
    for folder,pin in SEALS.items():
        if sha(folder/'delivery_manifest.json')!=pin:raise ValueError('Prior seal changed')
        if full:
            for n,m in read(folder/'delivery_manifest.json')['files'].items():
                if sha(folder/n)!=m['sha256'] or (folder/n).stat().st_size!=m['bytes']:raise ValueError('Prior archive changed: '+n)
    for n,pin in config['input_sha256'].items():
        if sha(ROOT/n)!=pin:raise ValueError('Probe source changed: '+n)
    if sha(OUT/'model.xml')!=config['common']['canonical_model_sha256']:raise ValueError('Model changed')
    cp=PRIOR/'run/checkpoints'/config['checkpoint']['label']
    if sha(cp/'manifest.json')!=config['checkpoint']['pin'] or sha(cp/'state.pt')!=config['checkpoint']['state_sha256']:
        raise ValueError('Frozen actor checkpoint changed')
    admission=PilotAdmission(PRIOR,PRIOR_PIN);admission.verify('F50');return admission

def load_policy(config,admission):
    from tools.learning.v4_checkpoint import read_checkpoint
    cp=config['checkpoint'];binding=admission.verify('F50')
    state,(u,pool,boundary,rngs)=read_checkpoint(PRIOR/'run/checkpoints'/cp['label'],expected_digest=cp['pin'],expected_binding=binding,admission=admission)
    verify_frozen_state(state['updater'],u._snapshot())
    if u.counts['critic']!=2000:raise ValueError('Expected original F2000 actor')
    warm=state['warm']['draws'];del state,pool,boundary,rngs
    return SimpleNamespace(updater=u,binding=binding,warm_draws=warm)

def prepare():
    if (OUT/'configuration.json').exists():raise FileExistsError('Already prepared')
    common=read(PRIOR/'configuration.json');(OUT/'model.xml').write_bytes((PRIOR/'model.xml').read_bytes())
    names=[PLAN]+[(OUT/n).relative_to(ROOT).as_posix() for n in ('deployment_profile.py','run_probe.py','test_profile.py','test_execution.py')]
    config=dict(version='pc09_deployment_contract_v1',purpose='frozen_deployment_only',authorization='继续 after specified PC-08 G50/F12.5 plan',
        common=common['common'],common_key=common['common_key'],attempts=attempt_specs(common['common']),
        checkpoint=read(PC07/'configuration.json')['checkpoints']['F2000'],input_sha256={n:sha(ROOT/n) for n in names},
        profile_contract=dict(G50='SEARCH or INSERT with normalized float32 sensed Fz <= -0.2, subject to original common permission',
            F12p5='same frozen F2000 actor, normalized deployment request times0.25; original actor_action preserved',F50='original',B2='zero/no network'),
        collector_origin=dict(path='tools/validation/run_v4_learning_pilot.py',sha256=sha(ROOT/'tools/validation/run_v4_learning_pilot.py'),
            changes='explicit profile session/permission, actor request mapping, attempt counters and deployment-only audit; same physics/reward/reference/stop loop'),
        max_new_episodes=8,prior_cumulative=200,cumulative_limit=208,formal_updates=0,published_transitions=0,
        max_cycles=14500,per_episode_wall_s=1200,training_admitted=False,scope='two development positions, frozen deployment sensitivity, not new-method training or unseen tests')
    admission=verify_sources(config,full=True);write(OUT/'configuration.json',config)
    print('Reading original full F2000 checkpoint; no physics or optimizer calls',flush=True)
    c=load_policy(config,admission)
    write(OUT/'checkpoint_read_gate.json',dict(passed=True,original_mode='F50',counts=c.updater.counts,fingerprints=c.updater.fingerprints(),
        original_binding=c.binding,checkpoint=config['checkpoint'],complete_original_state_equal=True,new_profile_restore_claimed=False,
        dynamic_episodes=0,new_gradient_batches=0,new_network_predictions=0,input_sha256=config['input_sha256']))
    verify_sources(config,full=True);print('Prepared exact8 matrix, original full checkpoint read verified; training false',flush=True)

def audit_physics(raw):
    from tools.validation.native313_matrix_audit import actual_stop_pass
    from tools.validation.run_contact_candidate_stop import physical_tail_pass
    from tools.validation.verify_admitted_collection import validate_outcome
    from deployment_profile import audit_rows
    if raw['scope']!='contact_gate_deployment_probe' or raw['reference_problems'] or raw['actual_reference_failed'] or raw['fault'] is not None:
        raise ValueError('Unqualified profile/reference execution')
    stopped=bool(actual_stop_pass(raw['stop_samples'],raw['events'],raw['stop_time'],raw['audit_end_time_s'],.0002)
        and physical_tail_pass(raw['stop_samples'],raw['audit_end_time_s'],.0002))
    validate_outcome(raw,stopped=stopped)
    if not stopped or not raw['outcome']['simulation_valid']:raise ValueError('Invalid/unstopped probe')
    return audit_rows(raw)

def rollout(config,c,spec,entry,ledger):
    """Explicit port of the frozen collector: only profile/action/mask changes."""
    from dataclasses import asdict
    from tools.learning.guarded_environment import LearningEnvironment,GuardCandidateConfig
    from tools.validation.run_contact_cases import ContactCase
    from tools.validation.run_v4_adapter_preflight import actual_reference_radius,make_session as wiring
    from tools.learning.outcome import classify_outcome
    from tools.validation.run_v4_learning_pilot import SEED
    from tools.validation.run_clearance_preflight import archive_episode
    from deployment_profile import ProfileSession,permissions,deployment_action
    common=config['common'];profile=spec['profile'];point=spec['case']
    env=session=None
    case=ContactCase(point['id'],point['x_um']*1e-6,point['y_um']*1e-6,0,0,-.004,.004)
    transitions=[];trace=[];actions=[];started=time.monotonic();before=c.updater.counts['critic'];policy=c.updater.fingerprints()['actor']
    calls=attempts=checks=0;maxradius=0.;actual_failed=False
    def costs():
        entry.update(control_cycles=getattr(session,'cycle_id',0),physical_substeps=getattr(env,'physical_steps',0),
            simulated_time_s=float(getattr(getattr(env,'data',None),'time',0.)),policy_calls=calls,
            policy_call_attempts=attempts,wall_seconds=time.monotonic()-started,
            unknown_cost_fields=[name for name,obj,attr in [('control_cycles',session,'cycle_id'),('physical_substeps',env,'physical_steps')]
                if not hasattr(obj,attr)])
    try:
        env=LearningEnvironment(guard_config=GuardCandidateConfig(**common['guard_config']),model_xml=(OUT/'model.xml').read_text(encoding='utf8'))
        base=wiring(env,'F50',common)
        session=ProfileSession(profile=profile,environment=env,mode='F50',controller_factory=base.controller_factory,
            finish_criteria=common['finish_criteria'],geometry_checker=base.geometry_checker)
        snap=session.reset(case,seed=SEED);trace.append(session.initial_trace_row)
        while not session.done:
            if session.cycle_id>=14500 or time.monotonic()-started>1200 or (OUT/'STOP').exists():raise RuntimeError('Registered bound/STOP; no retry')
            active=permissions(snap.policy_observation,profile)
            if active!=snap.residual_enabled:raise ValueError('Same-cycle session/profile permission differs')
            actor=[0.]*4
            if active and profile!='B2':
                attempts+=1;actor=c.updater.predict(np.asarray(snap.policy_observation,dtype=np.float32),deterministic=True)[0].tolist();calls+=1
            request=deployment_action(actor,profile).tolist()
            result=session.advance_cycle(request);trace.append(result.trace_row)
            radius=actual_reference_radius(snap,result.trace_row,session.initial)
            if radius is not None:
                checks+=1;maxradius=max(maxradius,radius)
                if radius>.00012+1e-12:
                    actual_failed=True;session._finish('REFERENCE_ACTUAL_LIMIT');session._cache=None;result.next_snapshot=session.prepare_cycle()
            log=result.action_log;log.update(actor_action=actor,profile=profile,deployment_multiplier=.25 if profile=='F12.5' else 1.)
            actions.append(log)
            transitions.append(dict(observation=snap.policy_observation,next_observation=result.next_snapshot.policy_observation,
                action=log['experience_action'],action_active=snap.residual_enabled,next_action_active=result.next_snapshot.residual_enabled,
                reward=result.reward_terms['total'],reward_terms={**dict(terminal=0.),**result.reward_terms},dt=result.dt,
                discount=math.exp(-result.dt/10),terminated=bool(result.done),truncated=False,
                cycle_force_N=result.cycle_peaks['force_N'],cycle_torque_G_Nm=result.cycle_peaks['torque_G_Nm'],
                advance_m=result.trace_row['position_m'][2]-session.initial[2],action_log=log,trace_row=result.trace_row,sampling_request=None))
            snap=result.next_snapshot
            if session.cycle_id%500==0:
                costs();reconcile_calls(ledger);write(OUT/'run/ledger.json',ledger)
                archive_episode(OUT/'run'/(spec['id']+'.partial.json.gz'),dict(trace=trace,actions=actions,transitions=transitions,
                    events=env.events,stop_samples=env.stop_samples,guard_facts=env.guard_facts))
                print(canonical(dict(id=spec['id'],cycles=session.cycle_id,reason=session.reason)),flush=True)
        source=session.adjudicate()
        outcome=classify_outcome(simulation_valid=source['simulation_valid'],physical_stopped=source['physical_stopped'],
            contact_guard=bool(env.guard_facts['contact_reasons']),motion_violation=bool(env.guard_facts['motion_reasons']),
            full_success=session.task_finished and session.reason=='GEOMETRIC_SUCCESS')
        problems=[e for e in session.controller.events if e['reason'] in ('SEARCH_REFERENCE_LIMIT','RESIDUAL_REFERENCE_INFEASIBLE','REFERENCE_ACTUAL_LIMIT')]
        costs()
        raw=dict(version='pc09_deployment_episode_v1',scope='contact_gate_deployment_probe',episode_id=spec['id'],profile=profile,mode=profile,
            compositor_mode='F50',policy_source_mode=None if profile=='B2' else 'F50',stage='deployment',case_id=point['id'],case=point,
            case_index=spec['case_index'],simulation_case=asdict(case),seed=SEED,qualification_sha256=ledger['qualification_sha256'],
            comparison_key=config['common_key'],optimizer_steps_start=before,optimizer_steps=c.updater.counts['critic'],policy_sha256=policy,
            checkpoint=None if profile=='B2' else config['checkpoint'],transitions=transitions,trace=trace,actions=actions,observation_schema=session.observations.schema,
            source_session_outcome=source,outcome=outcome,guard_facts=env.guard_facts,events=env.events,stop_samples=env.stop_samples,
            stop_time=session.stop_time,audit_end_time_s=float(env.data.time),task_end_time_s=session.task_end_time,peaks=env.peaks,
            final_session=dict(task_finished=session.task_finished,reason=session.reason,phase=env.phase),controller_events=session.controller.events,
            reference_problems=problems,actual_reference_failed=actual_failed,max_actual_reference_radius_m=maxradius,actual_reference_checks=checks,
            policy_calls=calls,policy_call_attempts=attempts,network_policy_calls=calls,control_cycles=session.cycle_id,physical_substeps=env.physical_steps,
            wall_seconds=entry['wall_seconds'],fault=None,training_admitted=False,published_transitions=0)
        entry.update(status='finished',outcome=outcome,reason=session.reason,ended_at=now(),reference_problems=problems)
        entry['archive_sha256']=archive_episode(OUT/'run'/(spec['id']+'.json.gz'),raw);reconcile_calls(ledger);write(OUT/'run/ledger.json',ledger)
        return raw
    except BaseException as exc:
        costs();entry.update(status='error',error=repr(exc),ended_at=now());reconcile_calls(ledger)
        # Commit the small original-error receipt before a potentially large archive.
        write(OUT/'run/ledger.json',ledger)
        try:
            archive_episode(OUT/'run'/(spec['id']+'.error.json.gz'),dict(trace=trace,actions=actions,transitions=transitions,
                events=getattr(env,'events',[]),stop_samples=getattr(env,'stop_samples',[]),guard_facts=getattr(env,'guard_facts',None),entry=entry))
        except Exception as archive_error:
            entry['partial_archive_error']=repr(archive_error);write(OUT/'run/ledger.json',ledger)
        raise

def qualify():
    config=read(OUT/'configuration.json');verify_sources(config,full=True)
    v=read(OUT/'verification.json');r=read(OUT/'review.json');gate=read(OUT/'checkpoint_read_gate.json')
    if not v['passed'] or not gate['passed'] or r['critical'] or r['important']:raise ValueError('Qualification evidence failed')
    if v['input_sha256']!=config['input_sha256'] or r['input_sha256']!=config['input_sha256']:raise ValueError('Source/test/review mismatch')
    q=dict(version='pc09_deployment_qualification_v1',evaluation_admitted=True,training_admitted=False,max_new_episodes=8,
        formal_updates=0,published_transitions=0,prior_cumulative=200,cumulative_limit=208,created_at=now(),
        evidence_sha256={n:sha(OUT/n) for n in ('configuration.json','model.xml','verification.json','verification.txt','review.json','checkpoint_read_gate.json')})
    write(OUT/'qualification.json',q);pin=sha(OUT/'qualification.json');write(OUT/'qualification_pin.json',dict(sha256=pin));print(pin)

def execute(pin):
    from tools.validation.run_clearance_preflight import archive_episode
    if not pin or sha(OUT/'qualification.json')!=pin:raise ValueError('Out-of-band qualification pin differs')
    q=read(OUT/'qualification.json')
    if not q['evaluation_admitted'] or q['training_admitted'] or q['max_new_episodes']!=8 or q['formal_updates']!=0:raise ValueError('Wrong capability/budget')
    for n,p in q['evidence_sha256'].items():
        if sha(OUT/n)!=p:raise ValueError('Pinned evidence changed: '+n)
    config=read(OUT/'configuration.json');admission=verify_sources(config,full=True);(OUT/'run').mkdir(exist_ok=False)
    ledger=dict(status='prepared',started_at=now(),episodes=[],max_new_episodes=8,prior_cumulative=200,cumulative_limit=208,
        policy_calls=0,policy_call_attempts=0,formal_updates=0,published_transitions=0,retry_allowed=False,qualification_sha256=pin,policy_read_gate=None)
    write(OUT/'run/ledger.json',ledger);zero=SimpleNamespace(updater=ZeroUpdater());frozen=None
    try:
        while True:
            if (OUT/'STOP').exists():ledger['status']='controlled_stop';break
            spec=next_spec(ledger,config['attempts'])
            if spec is None:ledger['status']='complete';break
            if sha(OUT/'qualification.json')!=pin or any(sha(OUT/n)!=p for n,p in q['evidence_sha256'].items()):raise ValueError('Pinned evidence changed during execution')
            verify_sources(config)
            if spec['profile']!='B2' and frozen is None:
                print('Reading frozen original F2000 for deployment; no optimizer',flush=True)
                frozen=load_policy(config,admission);ledger['policy_read_gate']=dict(counts=frozen.updater.counts,fingerprints=frozen.updater.fingerprints(),read_only=True)
                write(OUT/'run/ledger.json',ledger)
            c=zero if spec['profile']=='B2' else frozen;before=c.updater._snapshot()
            entry=dict(id=spec['id'],profile=spec['profile'],spec=spec,status='running',started_at=now(),policy_calls=0,policy_call_attempts=0)
            ledger['episodes'].append(entry);ledger['status']='running';write(OUT/'run/ledger.json',ledger)
            raw=rollout(config,c,spec,entry,ledger);audit=audit_physics(raw);verify_frozen_state(before,c.updater._snapshot());verify_sources(config)
            raw['evaluation_checks']=dict(state_unchanged=True,optimizer_updates=0,published_transitions=0,profile_rows=audit['rows'])
            entry['evaluation_checks']=raw['evaluation_checks'];entry['archive_sha256']=archive_episode(OUT/'run'/(spec['id']+'.json.gz'),raw)
            reconcile_calls(ledger);write(OUT/'run/ledger.json',ledger);del before,raw
    except BaseException as exc:
        ledger.update(status='error',error=repr(exc));reconcile_calls(ledger);write(OUT/'run/ledger.json',ledger);raise
    finally:
        reconcile_calls(ledger);ledger.update(ended_at=now(),unused_closed=8-len(ledger['episodes']),inputs_unchanged=False)
        try:verify_sources(config,full=True);ledger['inputs_unchanged']=True
        except Exception as exc:ledger['source_end_error']=repr(exc);ledger['status']='error'
        write(OUT/'run/ledger.json',ledger);print(canonical({k:v for k,v in ledger.items() if k!='episodes'}),flush=True)

if __name__=='__main__':
    os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'tmp/matplotlib_pc09'))
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('prepare','qualify','execute'));parser.add_argument('--pin');a=parser.parse_args()
    {'prepare':prepare,'qualify':qualify,'execute':lambda:execute(a.pin)}[a.action]()
