"""One-claim 137D learning qualification and bounded physical F50/S50 pilot."""
import argparse,gzip,hashlib,json,math,os,runpy,subprocess,sys,time
from pathlib import Path
from dataclasses import asdict
from tools.learning.v4_pilot_contract import ROOT,DELIVERY,PRIOR,PLAN,SEED,canonical,sha,read,learning_config,attempt_specs,permission
from tools.validation.run_clearance_preflight import write,now,archive_episode

CONTROL_PREFLIGHT=ROOT/'deliverables/paper_comparison/search_boundary_fix_20261006'
CONTROL_PREFLIGHT_PIN='ae124ffa9d47d2ed2719b64cbf1202241ded4287c5be842b61ea962b13c8e8e5'

def registered_common():
    """Rebind registration code only; preserve the physically verified control."""
    if sha(CONTROL_PREFLIGHT/'delivery_manifest.json')!=CONTROL_PREFLIGHT_PIN:raise ValueError('Control preflight seal changed')
    for name,r in read(CONTROL_PREFLIGHT/'delivery_manifest.json')['files'].items():
        if sha(CONTROL_PREFLIGHT/name)!=r['sha256']:raise ValueError('Control preflight evidence changed: '+name)
    preflight=read(CONTROL_PREFLIGHT/'configuration.json');common=preflight['common']
    before=dict(common['frozen_common_source_sha256'])
    # The inherited common list predates v4; the sealed preflight input list
    # already binds those active modules. Include both in the new common key.
    before.update({n:h for n,h in preflight['input_sha256'].items() if n.startswith('tools/') and n.endswith('.py')})
    after={n:sha(ROOT/n) for n in before}
    delta={n:dict(before=before[n],after=after[n]) for n in before if before[n]!=after[n]}
    allowed={'tools/learning/v4_pilot_contract.py','tools/validation/run_v4_learning_pilot.py'}
    if not set(delta)<=allowed:raise ValueError('Unexpected change since physical control preflight')
    common['frozen_common_source_sha256']=after
    return common,delta

def input_hashes():
    paths=list((ROOT/'tools').rglob('*.py'))+list((ROOT/'models').rglob('*.xml'))+list((ROOT/'assets').rglob('*.stl'))+list((ROOT/'tests').rglob('*.py'))
    paths += [ROOT/PLAN,PRIOR/'delivery_manifest.json',ROOT/'deliverables/paper_comparison/protocol_v4_20261004/protocol.json',CONTROL_PREFLIGHT/'delivery_manifest.json']
    return {p.relative_to(ROOT).as_posix():sha(p) for p in paths}

def learning_runtime_proof():
    from tools.learning.runtime import active_package
    from tools.validation.verify_residual_interface import qualified_runtime
    return qualified_runtime(active_package())

def verify_learning_runtime(expected):
    actual=learning_runtime_proof()
    if canonical(actual)!=canonical(expected):raise ValueError('CPU learning interpreter/dependencies/DLL proof changed')
    return actual

def verify_qualification_sources(config,verification,review):
    current=config['input_sha256'];before=review['reviewed_source_sha256']
    if verification.get('passed') is not True or verification.get('source_sha256')!=current or review.get('validated_source_sha256')!=current:
        raise ValueError('Tests/review fix validation describe different source versions')
    delta={k:dict(before=before.get(k),after=current.get(k)) for k in sorted(set(before)|set(current)) if before.get(k)!=current.get(k)}
    if review.get('fix_delta')!=delta:raise ValueError('Undocumented changes after independent review')

def check_qualification(q):
    exact=dict(version='v4_learning_qualification_v2',training_admitted=True,purpose='bounded_physical_pilot',
        tests_passed=True,review_critical=0,review_important=0,complete_restore_passed=True,independent_restore_passed=True,
        qualification_dynamic_episodes=0,formal_gradient_batches=0,max_new_episodes=28,max_formal_batches=4000,
        authorization='继续推进，如果没发现问题可以直接进入学习链准入和小规模训练',
        control_preflight_sha256=CONTROL_PREFLIGHT_PIN,prior_cumulative=145,cumulative_limit=173)
    if any(type(q.get(k)) is not type(v) or q[k]!=v for k,v in exact.items()):raise ValueError('Incomplete or changed learning qualification')

class PilotAdmission:
    def __init__(self,folder=DELIVERY,expected_digest=None):
        self.folder=Path(folder).resolve();self.expected_digest=expected_digest
        if expected_digest is None:raise ValueError('Out-of-band qualification pin required')
    def verify(self,mode):
        if sha(self.folder/'qualification.json')!=self.expected_digest:raise ValueError('Qualification changed')
        q=read(self.folder/'qualification.json');check_qualification(q)
        for name,digest in q['evidence_sha256'].items():
            if sha(self.folder/name)!=digest:raise ValueError('Qualification evidence changed: '+name)
        c=read(self.folder/'configuration.json')
        verify_qualification_sources(c,read(self.folder/'verification.json'),read(self.folder/'review.json'))
        if c['input_sha256']!=input_hashes():raise ValueError('Execution source changed')
        for name,digest in c['common']['frozen_common_source_sha256'].items():
            if sha(ROOT/name)!=digest:raise ValueError('Frozen dependency changed: '+name)
        if sha(self.folder/'model.xml')!=c['common']['canonical_model_sha256']:raise ValueError('Model changed')
        from tools.learning.runtime import verify_runtime,active_package
        from tools.evaluation.paper_comparison import comparison_key
        if comparison_key(verify_runtime(active_package()))!=c['common']['runtime_proof_sha256']:raise ValueError('Runtime changed')
        verify_learning_runtime(c['learning_runtime'])
        return dict(purpose='bounded_physical_pilot',mode=mode,qualification_sha256=self.expected_digest,
            config_sha256=hashlib.sha256(canonical(learning_config(mode)).encode()).hexdigest())

def new_ledger(specs):
    if len(specs)!=28:raise ValueError('Registered 28-case matrix required')
    return dict(status='prepared',started_at=now(),episodes=[],skipped=[],branches=dict(F50='ready',S50='ready'),
        max_new_episodes=28,prior_cumulative=145,cumulative_limit=173,formal_update_attempts=0,formal_updates=0,
        per_branch_updates=dict(F50=0,S50=0),policy_calls=0,independent_tests=0,retry_allowed=False)

def next_spec(ledger,specs):
    if ledger['status'] in ('error','controlled_stop','complete'):return None
    ids=[e['id'] for e in ledger['episodes']]
    if len(ids)!=len(set(ids)) or any(e['status']!='finished' for e in ledger['episodes']):raise RuntimeError('Unfinished/duplicate attempt cannot be retried')
    consumed=set(ids)|set(ledger['skipped']);known={s['id'] for s in specs}
    if not consumed<=known or len(ids)>28:raise RuntimeError('Unknown/excess attempt')
    for s in specs:
        if s['id'] in consumed:continue
        if ledger['branches'][s['mode']]!='ready':ledger['skipped'].append(s['id']);continue
        return s
    return None

def prepare(folder):
    folder=Path(folder)
    if (folder/'configuration.json').exists():raise FileExistsError('Prepared already')
    if sha(PRIOR/'delivery_manifest.json')!='536a599cd5b8baaab8fbb8951f8b1557a6eb40bc2d215f12603103d0a07a4673':raise ValueError('PC-03 changed')
    for name,r in read(PRIOR/'delivery_manifest.json')['files'].items():
        if sha(PRIOR/name)!=r['sha256']:raise ValueError('PC-03 file changed: '+name)
    from tools.learning.runtime import verify_runtime,active_package
    from tools.evaluation.paper_comparison import comparison_key
    from tools.model.clearance_task import build_task_xml
    common,delta=registered_common();xml=build_task_xml()
    if hashlib.sha256(xml.encode()).hexdigest()!=common['canonical_model_sha256']:raise ValueError('Common model differs')
    runtime=verify_runtime(active_package())
    if comparison_key(runtime)!=common['runtime_proof_sha256']:raise ValueError('Runtime not qualified')
    folder.mkdir(parents=True,exist_ok=True);(folder/'model.xml').write_text(xml,encoding='utf8',newline='\n')
    c=dict(version='v4_learning_pilot_v2',common=common,common_key=comparison_key(common),registration_source_delta=delta,
        control_preflight_sha256=CONTROL_PREFLIGHT_PIN,input_sha256=input_hashes(),runtime=runtime,learning_runtime=learning_runtime_proof(),
        methods={m:learning_config(m) for m in ('F50','S50')},attempts=attempt_specs(common),max_cycles=14500,
        per_episode_wall_s=1200,checkpoint_read_wall_s=300,prior_cumulative=145,cumulative_limit=173,max_formal_batches=4000)
    write(folder/'configuration.json',c);return c

def child(args,log,timeout):
    cmd=[sys.executable,'-X','utf8','-B','-m','tools.validation.run_v4_learning_pilot',*args]
    with Path(log).open('x',encoding='utf8') as f:
        result=subprocess.run(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=timeout)
    if result.returncode:raise RuntimeError('Independent process failed: '+str(log))

def probe(folder):
    """Numeric qualification only; never resets/steps a physical environment."""
    from tools.learning.v4_checkpoint import save_checkpoint
    ns=runpy.run_path(str(ROOT/'tests/learning/test_v4_checkpoint.py'))
    p=Path(folder)/'probe_v2';p.mkdir();c=ns['populated'](p/'chain');c.update(2)
    pin=save_checkpoint(c,p/'checkpoint');write(p/'request.json',dict(pin=pin,binding=c.binding))
    child(['--probe-read','--folder',str(folder)],p/'reader.log',300)
    obs=ns['observation']('F50',True);action=c.updater.predict(obs)[0].tolist();stats=c.update(1)[0];stats.pop('wall_s')
    from tools.learning.sac_checkpoint import _rng
    warm=_rng(c.warm_rng.bit_generator.state).uniform(-1,1,4).tolist()
    expected=dict(action=action,next_warm_action=warm,stats=stats,fingerprints=c.updater.fingerprints())
    if read(p/'reader_result.json')!=expected:raise ValueError('Independent next action/update differs')
    result=dict(complete_restore_passed=True,independent_restore_passed=True,dynamic_episodes=0,formal_batches=0,
        synthetic_batches_parent=3,synthetic_batches_reader=1,checkpoint_sha256=pin,next_step=expected)
    write(p/'result.json',result);return result

def probe_read(folder):
    from tools.learning.v4_checkpoint import load_checkpoint
    ns=runpy.run_path(str(ROOT/'tests/learning/test_v4_checkpoint.py'));p=Path(folder)/'probe_v2';r=read(p/'request.json')
    c=load_checkpoint(p/'checkpoint',expected_digest=r['pin'],expected_binding=r['binding'],output=p/'reader_chain')
    action=c.updater.predict(ns['observation']('F50',True))[0].tolist();stats=c.update(1)[0];stats.pop('wall_s')
    from tools.learning.sac_checkpoint import _rng
    warm=_rng(c.warm_rng.bit_generator.state).uniform(-1,1,4).tolist()
    write(p/'reader_result.json',dict(action=action,next_warm_action=warm,stats=stats,fingerprints=c.updater.fingerprints()))

def qualify(folder):
    folder=Path(folder);config=prepare(folder);probe(folder)
    verify_qualification_sources(config,read(folder/'verification.json'),read(folder/'review.json'))
    evidence={n:sha(folder/n) for n in ('configuration.json','model.xml','verification.txt','verification.json','verification.xml','review.json','reviewed_source.json','probe_v2/result.json','probe_v2/reader_result.json')}
    review=read(folder/'review.json')
    if review['critical'] or review['important']:raise ValueError('Unresolved independent review')
    result=read(folder/'probe_v2/result.json')
    q=dict(version='v4_learning_qualification_v2',purpose='bounded_physical_pilot',training_admitted=True,
        authorization='继续推进，如果没发现问题可以直接进入学习链准入和小规模训练',
        tests_passed=read(folder/'verification.json')['passed'],review_critical=review['critical'],review_important=review['important'],
        complete_restore_passed=result['complete_restore_passed'],independent_restore_passed=result['independent_restore_passed'],
        qualification_dynamic_episodes=0,formal_gradient_batches=0,max_new_episodes=28,max_formal_batches=4000,
        control_preflight_sha256=CONTROL_PREFLIGHT_PIN,prior_cumulative=145,cumulative_limit=173,
        evidence_sha256=evidence,created_at=now(),scope='rigid_candidate_common_task_only_development_pilot')
    check_qualification(q);write(folder/'qualification.json',q)
    pin=sha(folder/'qualification.json');write(folder/'qualification_pin.json',dict(sha256=pin));return pin

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
    session=make_session(env,mode,common)
    case=ContactCase(point['id'],point['x_um']*1e-6,point['y_um']*1e-6,0,0,-.004,.004)
    transitions=[];trace=[];actions=[];started=time.monotonic();before=c.updater.counts['critic'];policy=c.updater.fingerprints()['actor'];calls=0
    actual_failed=False;maxradius=0.;checks=0;raw=None
    try:
        snap=session.reset(case,seed=SEED);trace.append(session.initial_trace_row)
        while not session.done:
            if session.cycle_id>=14500 or time.monotonic()-started>1200 or (Path(stop_file) if stop_file else folder/'STOP').exists():raise RuntimeError('Registered physical bound/STOP; no retry')
            active=permission(snap.policy_observation,mode)
            if active!=snap.residual_enabled:raise ValueError('Session permission differs from schema')
            sampled=None
            if stage=='warmup':
                sampled=c.warm_action(session.cycle_id);requested=sampled if active else [0.]*4
            elif active:
                requested=c.updater.predict(np.asarray(snap.policy_observation,dtype=np.float32),deterministic=stage in ('final','restore'))[0].tolist();calls+=1
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

def checkpoint_gate(folder,c,label,pin):
    request=dict(mode=c.mode,label=label,pin=pin,qualification=c.binding['qualification_sha256'],fingerprints=c.updater.fingerprints(),counts=c.updater.counts)
    write(folder/'run'/(label+'.request.json'),request)
    child(['--checkpoint-read',label,'--folder',str(folder)],folder/'run'/(label+'.reader.log'),300)
    r=read(folder/'run'/(label+'.reader.json'))
    if r['fingerprints']!=request['fingerprints'] or r['counts']!=request['counts']:raise ValueError('Independent checkpoint state differs')

def checkpoint_read(folder,label):
    from tools.learning.v4_checkpoint import load_checkpoint
    r=read(folder/'run'/(label+'.request.json'));a=PilotAdmission(folder,r['qualification']);binding=a.verify(r['mode'])
    c=load_checkpoint(folder/'run/checkpoints'/label,expected_digest=r['pin'],expected_binding=binding,admission=a,output=folder/'run/readers'/label)
    write(folder/'run'/(label+'.reader.json'),dict(fingerprints=c.updater.fingerprints(),counts=c.updater.counts,replay_rows=len(c.replay),attempts=len(c.attempts)))

def execute(folder,pin):
    from tools.learning.v4_pilot_chain import V4Chain
    from tools.learning.v4_checkpoint import save_checkpoint
    folder=Path(folder);run=folder/'run';run.mkdir();config=read(folder/'configuration.json');specs=config['attempts'];ledger=new_ledger(specs);write(run/'ledger.json',ledger)
    try:
        a=PilotAdmission(folder,pin);chains={m:V4Chain(learning_config(m),output=run/'chains'/m,binding=a.verify(m),admission=a) for m in ('F50','S50')}
        if chains['F50'].origin!=chains['S50'].origin:raise ValueError('F/S origins differ')
        ledger['origin_fingerprints']=chains['F50'].origin;frozen={}
        for m,c in chains.items():
            label=m+'_zero';digest=save_checkpoint(c,run/'checkpoints'/label);checkpoint_gate(folder,c,label,digest)
        while True:
            if (folder/'STOP').exists():ledger['status']='controlled_stop';break
            s=next_spec(ledger,specs)
            if s is None:break
            mode=s['mode'];c=chains[mode];a.verify(mode)
            if s['stage'] in ('final','restore') and c.updater.counts['critic']!=2000:raise ValueError('Evaluation checkpoint not at registered update count')
            entry=dict(id=s['id'],spec=s,status='running',started_at=now());ledger['episodes'].append(entry);ledger['status']='running';write(run/'ledger.json',ledger)
            if s['stage']=='restore':
                request=dict(spec=s,checkpoint=frozen[mode],qualification=pin)
                write(run/(s['id']+'.request.json'),request)
                child(['--restore-episode',s['id'],'--folder',str(folder)],run/(s['id']+'.child.log'),1500)
                raw=json.loads(gzip.decompress((run/(s['id']+'.json.gz')).read_bytes()));audit_evaluation(raw)
                baseline=json.loads(gzip.decompress((run/('final_'+mode+'_'+s['case']['id']+'.json.gz')).read_bytes()))
                equal=all(raw[k]==baseline[k] for k in ('trace','actions','transitions','outcome','controller_events','events','stop_samples','peaks'))
                if not equal:raise ValueError('Independent physical replay differs')
                entry.update(status='finished',outcome=raw['outcome'],archive_sha256=sha(run/(s['id']+'.json.gz')),restore_exact=True,
                    control_cycles=raw['control_cycles'],physical_substeps=raw['physical_substeps'],policy_calls=raw['policy_calls'],wall_seconds=raw['wall_seconds'],ended_at=now())
                ledger['policy_calls']+=raw['policy_calls']
            else:
                if s['stage'] in ('warmup','online'):c.begin(s['stage'],s['case_index'])
                raw=rollout(folder,c,s,entry,ledger,checkpoint=frozen.get(mode))
                if s['stage'] in ('warmup','online'):
                    receipt=c.publish(raw);entry['publication']=receipt
                    if c.failed:raise ValueError('Invalid whole-episode publication')
                    if c.stop_reason:ledger['branches'][mode]=c.stop_reason
                    elif s['stage']=='online':
                        def before(chain):
                            if (folder/'STOP').exists() or ledger['formal_update_attempts']>=4000:raise RuntimeError('STOP/update budget')
                            ledger['formal_update_attempts']+=1;write(run/'ledger.json',ledger)
                        def after(chain,stats):
                            ledger['formal_updates']+=1;ledger['per_branch_updates'][mode]=chain.updater.counts['critic']
                        c.update(500,before_update=before,after_update=after)
                        write(run/(mode+'_history.json'),c.history);write(run/'ledger.json',ledger)
                    label=mode+'_'+s['stage']+'_'+str(s['case_index']);digest=save_checkpoint(c,run/'checkpoints'/label);checkpoint_gate(folder,c,label,digest)
                    entry['checkpoint']=dict(label=label,pin=digest)
                    if c.updater.counts['critic']==2000:frozen[mode]=entry['checkpoint']
                else:
                    audit_evaluation(raw)
                    if raw['outcome']['task_outcome'] in ('CONTACT_GUARD','MOTION_VIOLATION'):ledger['branches'][mode]=raw['outcome']['task_outcome']
            write(run/'ledger.json',ledger);a.verify(mode)
        for m in ('F50','S50'):a.verify(m)
        ledger.update(status='complete' if len(ledger['episodes'])==28 and not ledger['skipped'] else 'controlled_stop',
            ended_at=now(),unused_closed=28-len(ledger['episodes']),inputs_unchanged=True)
        write(run/'ledger.json',ledger);return ledger
    except BaseException as exc:
        if 'chains' in locals():
            ledger['per_branch_updates']={m:c.updater.counts['critic'] for m,c in chains.items()}
            ledger['formal_updates']=sum(ledger['per_branch_updates'].values())
            for m,c in chains.items():
                try:write(run/(m+'_history_at_error.json'),dict(counts=c.updater.counts,attempts=c.update_attempts,history=c.history))
                except Exception:pass
        ledger.update(status='error',error=repr(exc),ended_at=now(),unused_closed=28-len(ledger['episodes']))
        write(run/'ledger.json',ledger);raise

def restore_episode(folder,key):
    from tools.learning.v4_checkpoint import load_checkpoint
    r=read(folder/'run'/(key+'.request.json'));s=r['spec'];a=PilotAdmission(folder,r['qualification']);cp=r['checkpoint']
    c=load_checkpoint(folder/'run/checkpoints'/cp['label'],expected_digest=cp['pin'],expected_binding=a.verify(s['mode']),admission=a,
        output=folder/'run/restore_chains'/key)
    # The parent owns the only durable budget claim. Child progress uses its own
    # ledger file, avoiding concurrent overwrites of the parent's matrix ledger.
    child_folder=folder/'run/restore_runs'/key;child_folder.mkdir(parents=True)
    (child_folder/'model.xml').write_bytes((folder/'model.xml').read_bytes());write(child_folder/'configuration.json',read(folder/'configuration.json'))
    (child_folder/'run').mkdir();entry=dict(id=key,spec=s,status='running',started_at=now());ledger=dict(episodes=[entry],policy_calls=0)
    raw=rollout(child_folder,c,s,entry,ledger,checkpoint=cp,stop_file=folder/'STOP')
    archive_episode(folder/'run'/(key+'.json.gz'),raw)

def main():
    p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--qualify',action='store_true');g.add_argument('--execute',action='store_true');g.add_argument('--probe-read',action='store_true')
    g.add_argument('--checkpoint-read');g.add_argument('--restore-episode');p.add_argument('--folder',type=Path,default=DELIVERY);p.add_argument('--qualification-pin')
    args=p.parse_args()
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime();os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'tmp/matplotlib_v4_learning_pilot'))
    if args.qualify:print(qualify(args.folder),flush=True)
    elif args.execute:
        if not args.qualification_pin:p.error('Explicit qualification pin required')
        print(canonical(execute(args.folder,args.qualification_pin)),flush=True)
    elif args.probe_read:probe_read(args.folder)
    elif args.checkpoint_read:checkpoint_read(args.folder,args.checkpoint_read)
    else:restore_episode(args.folder,args.restore_episode)

if __name__=='__main__':main()
