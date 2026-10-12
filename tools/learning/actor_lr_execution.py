"""Authorized numerical validation, conditional offline A/B, frozen evaluation."""
from copy import deepcopy
import gzip
import io
import json
from pathlib import Path
import time
import numpy as np
import torch
from .actor_lr_contract import (ROOT,DELIVERY,ORIGIN,OLD,CASE_NAMES,execution_config,verify_candidate,
    require_authorization,branch_binding,digest,read)
from .actor_lr_budget import ComparisonLedger
from .actor_lr_engine import (OfflineBranch,ComparisonUpdater,read_origin,inactive_batch,save_checkpoint,
    load_checkpoint,verify_a_reproduction,reproduction_fields_equal)
from .actor_lr_origin import read_pinned_state
from .sac_checkpoint import _same,_tensor,_optimizer,_audit_physics
from .admitted_collection import _write_json as write
from .bounded_contact import BoundedAdmission,SEED
from .bounded_cycle import BoundedEvaluationCollector,cases
from .episode_rules import FORCE_ONLY
from .engineering_evaluation import FrozenPolicy,episode_metrics
from .policy_distribution_diagnostics import diagnose

DIAGNOSTIC=ROOT/'deliverables/learning_chain/b2_actor_lr_implementation_20260930/diagnostic_states.json'


def identity(candidate_pin,authorization_pin):
    return dict(candidate_sha256=candidate_pin,authorization_sha256=authorization_pin)


def assert_validation_proof(ledger,run,*,allow_active=False):
    if allow_active:
        ledger._validate()
        if ledger._write_failed or ledger.state['status']!='healthy':raise RuntimeError('Healthy evaluation ledger required')
        if ledger.state['active'] is not None and ledger.state['attempts'][ledger.state['active']]['kind']!='physical':
            raise RuntimeError('Only current physical reservation allowed during publication')
    else:ledger._healthy()
    path=Path(run)/'real_validation.json';proof=read(path)
    if (digest(path)!=ledger.state['gates'].get('real_validation') or proof.get('passed') is not True or
        any(proof.get(k)!=ledger.state[k] for k in ('candidate_sha256','authorization_sha256')) or
        proof.get('synthetic_transactions')!=4 or proof.get('test_forward_states')!=8 or
        ledger._count('synthetic','shared',finished=True)!=4 or ledger._count('test_forward','shared',finished=True)!=8):
        raise ValueError('Complete bound numerical validation evidence required')


def _private_restore(saved,updater):
    reference=updater._snapshot()
    if saved.keys()!=reference.keys() or saved['policy'].keys()!=reference['policy'].keys():raise ValueError('Private learned state missing')
    for k in reference['policy']:_tensor(saved['policy'][k],reference['policy'][k])
    _tensor(saved['alpha'],reference['alpha']);_tensor(saved['rng'],reference['rng']);torch.Generator().set_state(saved['rng'])
    for k,opt in zip(('critic','actor','temperature'),updater._optimizers()):_optimizer(saved[k],opt,saved['counts'][k])
    updater._restore(deepcopy(saved));updater._finite_state()


def real_validation(origin,plan,ledger,run,candidate_pin,authorization_pin):
    """Four charged private transactions; formal branches remain at zero."""
    a=OfflineBranch(origin,plan,'A',candidate_pin,authorization_pin)
    b=OfflineBranch(origin,plan,'B',candidate_pin,authorization_pin)
    batch=a.next_batch();before_a=a.updater._snapshot();before_b=b.updater._snapshot()
    results={}
    for name,engine in (('active_A',a),('active_B',b)):
        token=ledger.reserve('synthetic','shared',name)
        result=engine.updater.update(batch.actor,critic_batch=batch.critic,exact_targets=(batch.targets,batch.mask))
        if result['active_rows']<=0:raise ValueError('Active numerical validation required')
        ledger.finish(token,dict(completed=True,counts=engine.updater.counts));results[name]=result
    sa,sb=a.updater._snapshot(),b.updater._snapshot()
    if any(not _same(sa[k],sb[k]) for k in ('critic','temperature','alpha','rng','counts')):
        raise ValueError('First critic/temperature transaction differs between A and B')
    delta_a=[];delta_b=[]
    for key in sa['policy']:
        if key.startswith('actor.'):
            da=sa['policy'][key]-before_a['policy'][key];db=sb['policy'][key]-before_b['policy'][key]
            if not torch.allclose(db,.1*da,rtol=0,atol=2e-7):raise ValueError('First actor delta does not match separate rate')
            delta_a.append(da.flatten());delta_b.append(db.flatten())
        elif not torch.equal(sa['policy'][key],sb['policy'][key]):raise ValueError('First critic or target weights differ')
    norm_a=float(torch.linalg.vector_norm(torch.cat(delta_a)));norm_b=float(torch.linalg.vector_norm(torch.cat(delta_b)))
    if norm_a<=0 or not .099<=norm_b/norm_a<=.101:raise ValueError('First actor norm ratio differs')
    # Save/load a privately updated branch snapshot without another update.
    stream=io.BytesIO();torch.save(sb,stream);stream.seek(0)
    saved=torch.load(stream,map_location='cpu',weights_only=True)
    restored=ComparisonUpdater(execution_config('B'));_private_restore(saved,restored)
    if not _same(saved,restored._snapshot()):raise ValueError('Private saved learning state differs')
    unchanged=restored._snapshot()
    try:restored._restore(deepcopy(sa))
    except ValueError:pass
    else:raise ValueError('Cross-branch optimizer rate was accepted')
    if not _same(unchanged,restored._snapshot()):raise ValueError('Rejected restore mutated destination')
    inactive=ComparisonUpdater(execution_config('A'));inactive._restore(deepcopy(before_a));before=inactive._snapshot()
    token=ledger.reserve('synthetic','shared','inactive_A')
    inactive.update(inactive_batch(batch.actor),critic_batch=inactive_batch(batch.critic),exact_targets=(batch.targets,batch.mask))
    after=inactive._snapshot()
    if (inactive.counts!=dict(critic=1,target=1,actor=0,temperature=0) or
        any(not _same(before[k],after[k]) for k in ('actor','alpha','temperature')) or
        any(not torch.equal(v,after['policy'][k]) for k,v in before['policy'].items() if k.startswith('actor.'))):
        raise ValueError('Inactive actor/temperature transaction changed state')
    ledger.finish(token,dict(completed=True,counts=inactive.counts))
    rollback=ComparisonUpdater(execution_config('A'));rollback._restore(deepcopy(before_a));before=rollback._snapshot()
    token=ledger.reserve('synthetic','shared','injected_temperature_failure')
    original_step=rollback.temperature_optimizer.step
    def injected(*a,**k):raise RuntimeError('actor_lr_expected_injected_failure')
    rollback.temperature_optimizer.step=injected
    try:
        try:rollback.update(batch.actor,critic_batch=batch.critic,exact_targets=(batch.targets,batch.mask))
        except RuntimeError as exc:
            if 'actor_lr_expected_injected_failure' not in str(exc):raise
        else:raise ValueError('Injected transaction did not fail')
    finally:rollback.temperature_optimizer.step=original_step
    if not rollback.failed or not _same(before,rollback._snapshot()):raise ValueError('Failed transaction did not exactly roll back')
    ledger.finish(token,dict(completed=True,expected_failure=True,rollback_exact=True))
    states=np.asarray([r['observation'] for r in read(DIAGNOSTIC)['states'][:4]],dtype=np.float32)
    for name,updater in (('predict_A',a.updater),('predict_B',restored)):
        token=ledger.reserve('test_forward','shared',name,units=4);before=updater._snapshot()
        action,_=updater.predict(states,deterministic=True)
        if action.shape!=(4,4) or not np.isfinite(action).all() or not _same(before,updater._snapshot()):
            raise ValueError('Deterministic test forward changed state or emitted invalid action')
        ledger.finish(token,dict(completed=True,state_unchanged=True))
    proof=dict(passed=True,**identity(candidate_pin,authorization_pin),synthetic_transactions=4,test_forward_states=8,
        first_actor_delta_norm_ratio=norm_b/norm_a,delta_absolute_tolerance=2e-7,
        critic_temperature_first_transaction_exact=True,inactive_actor_temperature_unchanged=True,
        injected_failure_rollback_exact=True,saved_restore_exact=True,cross_branch_rejected=True,
        deterministic_state_unchanged=True,formal_states_untouched=True,results=results)
    write(Path(run)/'real_validation.json',proof);ledger.complete_validation(digest(Path(run)/'real_validation.json'))
    return proof


def formal_branches(origin,plan,ledger,run,candidate_pin,authorization_pin):
    assert_validation_proof(ledger,run);frozen={}
    for branch in ('A','B'):
        engine=OfflineBranch(origin,plan,branch,candidate_pin,authorization_pin)
        for i in range(500):
            engine.update_one(ledger)
            if (i+1)%25==0:
                write(Path(run)/'progress.json',dict(stage=branch+'_training',completed=i+1,wall_timestamp=time.time()))
                print(json.dumps(dict(stage=branch,completed=i+1)),flush=True)
        if branch=='A':
            proof=verify_a_reproduction(engine)
            proof.update(**identity(candidate_pin,authorization_pin));write(Path(run)/'a_reproduction.json',proof)
        pin=save_checkpoint(engine,Path(run)/('checkpoint_'+branch))
        frozen[branch]=dict(path='checkpoint_'+branch,sha256=pin,updates=500)
        write(Path(run)/'frozen.json',frozen)
        if branch=='A':ledger.reproduce_a(digest(Path(run)/'a_reproduction.json'))
        else:ledger.freeze_b(pin)
    return frozen


def fixed_diagnostics(origin,plan,ledger,run,frozen,candidate_pin,authorization_pin):
    selected=read(DIAGNOSTIC)['states']
    if len(selected)!=256 or len({(r['episode'],r['index']) for r in selected})!=256:raise ValueError('256 fixed unique states required')
    archives={key:json.loads(gzip.decompress(value)) for key,value in origin['archives'].items()}
    for row in selected:
        raw=archives[row['episode']]
        transition=raw['transitions'][row['index']]
        if transition['action_active'] is not True or row['observation']!=transition['observation']:raise ValueError('Fixed active diagnostic state differs')
    states=torch.tensor([r['observation'] for r in selected],dtype=torch.float32);parameters={}
    for role in ('initial','A','B'):
        if role=='initial':updater=OfflineBranch(origin,plan,'A',candidate_pin,authorization_pin).updater
        else:_,updater=load_checkpoint(Path(run)/frozen[role]['path'],frozen[role]['sha256'],origin,plan,role,candidate_pin,authorization_pin)
        before=updater._snapshot();token=ledger.reserve('diagnostic',role,'fixed_256_states',units=256)
        with torch.no_grad():mean,log_std,_=updater.policy.actor.get_action_dist_params(states)
        if mean.shape!=(256,4) or log_std.shape!=(256,4) or not _same(before,updater._snapshot()):raise ValueError('Actor diagnostic changed state')
        parameters[role]=dict(mean=mean.tolist(),log_std=log_std.tolist())
        # diagnose checks all values for finiteness and locked log_std bounds.
        for mu,ls in zip(parameters[role]['mean'],parameters[role]['log_std']):diagnose(mu,ls,mu,ls)
        ledger.finish(token,dict(completed=True,state_unchanged=True))
    reports={}
    for role in ('A','B'):
        reports[role]=[diagnose(rm,rl,mu,ls) for rm,rl,mu,ls in zip(parameters['initial']['mean'],
            parameters['initial']['log_std'],parameters[role]['mean'],parameters[role]['log_std'])]
    write(Path(run)/'diagnostics.json',dict(**identity(candidate_pin,authorization_pin),state_selection_sha256=digest(DIAGNOSTIC),
        parameters=parameters,reports=reports,states_per_role=256,critic_forward_count=0,
        deterministic_is_tanh_mean_not_expected_action=True))
    ledger.begin_evaluation({k:v['sha256'] for k,v in frozen.items()},digest(Path(run)/'diagnostics.json'))


def verify_evaluation_gate(ledger,run,candidate_pin,authorization_pin):
    assert_validation_proof(ledger,run,allow_active=True);frozen=read(Path(run)/'frozen.json')
    if set(frozen)!={'A','B'} or ledger.state['phase']!='evaluation':raise ValueError('Fixed A/B evaluation gate missing')
    proof=read(Path(run)/'a_reproduction.json')
    if (digest(Path(run)/'a_reproduction.json')!=ledger.state['gates']['a_reproduced'] or proof.get('learning_exact') is not True or
        any(proof.get(k)!=v for k,v in identity(candidate_pin,authorization_pin).items()) or
        ledger.state['gates']['b_frozen']!=frozen['B']['sha256'] or
        ledger.state['gates']['evaluation_checkpoints']!={k:v['sha256'] for k,v in frozen.items()}):raise ValueError('Bound A reproduction or frozen checkpoint gate differs')
    diagnostics=read(Path(run)/'diagnostics.json')
    if (digest(Path(run)/'diagnostics.json')!=ledger.state['gates']['diagnostics'] or
        diagnostics.get('state_selection_sha256')!=digest(DIAGNOSTIC) or
        any(diagnostics.get(k)!=v for k,v in identity(candidate_pin,authorization_pin).items()) or diagnostics.get('states_per_role')!=256):
        raise ValueError('Complete bound diagnostics required')
    return frozen


class ComparisonAdmission(BoundedAdmission):
    episode_rules=FORCE_ONLY
    updater_type=ComparisonUpdater
    def __init__(self,candidate_pin,authorization_pin,branch,ledger):
        self.expected_digest=candidate_pin;self.authorization_digest=authorization_pin;self.branch=branch;self.ledger=ledger;self.verify()
    def verify(self,case=None):
        self.ledger.check_execution()
        require_authorization(self.expected_digest,self.authorization_digest);verify_candidate(self.expected_digest)
        if (self.ledger.state['candidate_sha256']!=self.expected_digest or self.ledger.state['authorization_sha256']!=self.authorization_digest):
            raise ValueError('Evaluation ledger identity differs')
        verify_evaluation_gate(self.ledger,DELIVERY/'run',self.expected_digest,self.authorization_digest)
        if case is not None and case not in cases():raise ValueError('Only four registered 100um development points permitted')
        self._record=dict(capability='actor_lr_frozen_development_evaluation_v1',config=execution_config(self.branch),
            **identity(self.expected_digest,self.authorization_digest),branch=self.branch,
            synthetic_only=False,collection_admitted=False,update_admitted=False,evaluation_admitted=True)
        return deepcopy(self._record)


def evaluate_worker(candidate_pin,authorization_pin,branch):
    run=DELIVERY/'run';ledger=ComparisonLedger.load(run/'ledger.json',candidate_pin,authorization_pin)
    from tools.validation.run_actor_lr_comparison import execution_guard
    ledger.set_execution_guard(execution_guard(run/('eval_process_'+branch)))
    try:
        frozen=verify_evaluation_gate(ledger,run,candidate_pin,authorization_pin);origin,plan=read_origin()
        state,updater=load_checkpoint(run/frozen[branch]['path'],frozen[branch]['sha256'],origin,plan,branch,candidate_pin,authorization_pin)
        # Independently recheck actual learned A bytes in each restored process.
        astate,_=load_checkpoint(run/frozen['A']['path'],frozen['A']['sha256'],origin,plan,'A',candidate_pin,authorization_pin)
        manifest=read(ORIGIN/'manifest.json');path=OLD/'run/training/checkpoints/train_03'
        historical=read_pinned_state(path,manifest['archived_inputs_sha256'][(path/'manifest.json').relative_to(ROOT).as_posix()])
        if not reproduction_fields_equal(astate,historical):raise ValueError('Restored A no longer reproduces history')
        permit=ComparisonAdmission(candidate_pin,authorization_pin,branch,ledger)
        output=run/('evaluation_'+branch);output.mkdir(exist_ok=False)
        collector=BoundedEvaluationCollector(admission=permit,output=output/'episodes',updater=updater,
            method='sac',checkpoint_sha256=frozen[branch]['sha256'])
        before=updater._snapshot();results=[]
        try:
            for case in cases():
                token=ledger.reserve('physical',branch,case['name'])
                collector.start(case['name'],case=case,seed=SEED)
                while collector.active:
                    ledger.check_execution()
                    collector.collect(FrozenPolicy(updater),500,deterministic=True)
                    write(run/'progress.json',dict(stage=branch+'_evaluation',case=case['name'],cycles=collector._record['steps'],wall_timestamp=time.time()))
                raw=json.loads(gzip.decompress((collector.output/case['name']/'episode.json.gz').read_bytes()))
                receipt=collector.attempts[-1];facts=raw['guard_facts'];_audit_physics(raw)
                if (receipt['archive_sha256']!=digest(collector.output/case['name']/'episode.json.gz') or
                    read(collector.output/case['name']/'status.json')!=receipt or raw['training_admitted'] is not False or
                    receipt['committed']!=0 or len(collector.replay) or not _same(before,updater._snapshot())):
                    raise ValueError('Evaluation archive, replay isolation or learning state differs')
                row=dict(case=case['name'],completed=True,**episode_metrics(raw),
                    guard_hit=bool(facts['contact_reasons'] or facts['motion_reasons'] or facts['invalid_reasons']))
                results.append(row);write(output/'results.json',results)
                ledger.finish(token,row)
                if ledger.state['status']!='healthy':
                    write(output/'verification.json',dict(training_state_unchanged=True,all_points_completed=False))
                    return 20 if ledger.state['status']=='stopped' else 1
                if collector._blocked or not FORCE_ONLY.accepts(raw):raise ValueError('Complete evaluation eligibility audit failed')
            write(output/'verification.json',dict(training_state_unchanged=True,all_points_completed=True,restored_checkpoint_sha256=frozen[branch]['sha256']))
            return 0
        except BaseException as exc:
            if collector.active:collector._abort(exc)
            collector.retain_failure(exc);raise
        finally:write(output/'attempts.json',collector.attempts)
    except BaseException as exc:
        ledger.fail(repr(exc));write(run/'failure.json',dict(error=repr(exc),role=branch));raise
    finally:write(run/'accounting.json',ledger.accounting())


def execute_worker(candidate_pin,authorization_pin):
    from tools.validation.run_actor_lr_comparison import child_command,supervise,execution_guard,UnconfirmedWorkerStop
    run=DELIVERY/'run';run.mkdir(exist_ok=False);ledger=ComparisonLedger.create(run/'ledger.json',candidate_pin,authorization_pin)
    ledger.set_execution_guard(execution_guard(DELIVERY))
    try:
        origin,plan=read_origin()
        real_validation(origin,plan,ledger,run,candidate_pin,authorization_pin)
        frozen=formal_branches(origin,plan,ledger,run,candidate_pin,authorization_pin)
        fixed_diagnostics(origin,plan,ledger,run,frozen,candidate_pin,authorization_pin)
        for branch in ('A','B'):
            code=supervise(child_command(candidate_pin,authorization_pin,branch),run/('eval_process_'+branch))
            ledger=ComparisonLedger.load(run/'ledger.json',candidate_pin,authorization_pin)
            if code==20 and ledger.state['status']=='stopped':return 20
            if code!=0:raise RuntimeError('Restored evaluation process failed: '+str(code))
        ledger.complete()
        results={role:read(run/('evaluation_'+role)/'results.json') for role in ('A','B')}
        success={role:sum(r['success'] for r in rows) for role,rows in results.items()}
        write(run/'completed.json',dict(**identity(candidate_pin,authorization_pin),status='execution_complete',
            accounting=ledger.accounting(),success=success,initial_required_success=4,
            candidate_retains_initial_ability=success['B']==4,developer_only=True,
            fixes_2500_batch_online_failure_not_established=True,b2_complete=False))
        return 0
    except UnconfirmedWorkerStop as exc:
        # A descendant might still own an active charged reservation. Preserve
        # its ledger and request stop through the child's registered guard.
        write(run/'supervision_uncertain.json',dict(error=repr(exc),worker_stop_confirmed=False,retry_allowed=False))
        raise
    except BaseException as exc:
        # Child failures can leave newer charged attempts than the parent's
        # pre-launch in-memory ledger. Never overwrite them with stale state.
        ledger=ComparisonLedger.load(run/'ledger.json',candidate_pin,authorization_pin)
        ledger.fail(repr(exc));write(run/'failure.json',dict(error=repr(exc)));raise
    finally:
        ledger=ComparisonLedger.load(run/'ledger.json',candidate_pin,authorization_pin)
        write(run/'accounting.json',ledger.accounting())
