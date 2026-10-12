"""Offline terminal evidence audit. All physical/neural/optimizer calls blocked."""
from copy import deepcopy
import datetime,gzip,hashlib,io,json,os,sys
from pathlib import Path
import numpy as np
import validation_contract as C
os.environ['MPLCONFIGDIR']=str(C.ROOT/'tmp/learning_mpl_cache')
pins=C.read(C.HERE/'execution_pins.json');C.require_authorization(pins['binding_sha256'],pins['authorization_sha256'])
from run_validation import select_runtime
select_runtime()
import torch,mujoco
calls=dict(model_forward=0,optimizer=0,physics=0)
def forbidden(kind):
    def fail(*a,**kw):calls[kind]+=1;raise AssertionError('Offline audit forbids '+kind)
    return fail
torch.nn.Module._call_impl=forbidden('model_forward');torch.optim.Adam.step=forbidden('optimizer')
for name in ('mj_step','mj_step1','mj_step2','mj_forward','mj_resetData','mj_resetDataKeyframe'):setattr(mujoco,name,forbidden('physics'))
import learning_runtime as R
from tools.learning.sac_checkpoint import _same,_audit_physics,_replay_state,_tensor,_optimizer
from tools.learning.sac_update import tensor_digest
from tools.learning.engineering_evaluation import episode_metrics
from tools.learning.audited_replay import AuditedReplay
from tools.learning.episode_rules import FORCE_ONLY
from tools.learning.boundary_targets import BoundaryIndex
from sampling_runtime import audit_sampling

def check(value,message):
    if not value:raise ValueError(message)

def audit_checkpoint(path,ledger):
    m=C.read(path/'manifest.json');n=m['batches'];check(n in (500,1000,1500,2000,2500),'Unexpected checkpoint boundary')
    data=(path/'state.pt').read_bytes();check(hashlib.sha256(data).hexdigest()==m['state_sha256'],'Checkpoint payload digest differs')
    s=torch.load(io.BytesIO(data),map_location='cpu',weights_only=True);arm=m['arm']
    R.check_snapshot_identity(s,arm,ledger.state['binding_sha256'],ledger.state['authorization_sha256'])
    R.verify_dataset_bytes(s['dataset'],s['dataset_bytes'],s['dataset_sha256'])
    check(s['dataset_sha256']==m['dataset_sha256']==ledger.state['datasets'][arm]['manifest_sha256'],'Checkpoint data qualification differs')
    check(s['references'][:4]==s['dataset']['references'],'Checkpoint preflight references changed')
    check(len(s['references'])==len(s['archives'])==4+(n-1)//500,'Checkpoint audited credit differs')
    b=R.Branch.__new__(R.Branch);b.arm=arm;b.ledger=ledger;b.manifest=s['dataset'];b.manifest_pin=s['dataset_sha256'];b.dataset_bytes=s['dataset_bytes']
    b.replay=AuditedReplay(capacity=156000);b.index=BoundaryIndex(rules=FORCE_ONLY);b.refs=[];b.archives={}
    for i,ref in enumerate(s['references']):b.append_archive(ref,s['archives'][ref['id']],0 if i<4 else 500*(i-3))
    check(_same(_replay_state(b.replay),s['replay']) and _same(R.index_state(b.index),s['boundary_index']),'Checkpoint complete replay/index differs')
    history=s['history'];C.canonical(history);R.validate_counts(s['updater']['counts'],history,n)
    saved_history=C.read(C.HERE/'run'/('history_'+arm+'.json'))
    check(history==saved_history[:n],'Checkpoint update history differs from durable history')
    rr=R.rng(2);br=R.rng(3);episodes=b.replay._state.episodes
    for i,row in enumerate(history):
        count=4+i//500;prefix=episodes[:count];keys=[k for k,_ in prefix];arrays=dict(prefix)
        ends=np.cumsum([len(a['rewards']) for _,a in prefix]);starts=np.r_[0,ends[:-1]]
        uniform=rr.integers(0,int(ends[-1]),size=256);owners=np.searchsorted(ends,uniform,side='right')
        base=tuple((keys[o],int(j-starts[o])) for o,j in zip(owners,uniform))
        candidates=[(k,b.index.entries[k][2]) for k in keys if b.index.entries[k][2] is not None]
        boundary=tuple(candidates[int(j)] for j in br.integers(0,len(candidates),size=16))
        check(row['episode_count']==count and row['replay_size']==int(ends[-1]) and row['critic_sample_sha256']==R.sample_signature(base[:240]+boundary) and
            row['active_rows']==sum(bool(arrays[k]['action_active'][j,0]) for k,j in base),'Update sampling/permission history differs')
    check(rr.bit_generator.state==s['rng']['replay'] and br.bit_generator.state==s['rng']['boundary'],'Complete sampling RNG endpoint differs')
    u=R.Updater(C.config(arm));reference=u._snapshot();saved=s['updater']
    check(saved.keys()==reference.keys() and saved['policy'].keys()==reference['policy'].keys(),'Incomplete updater checkpoint')
    for k in reference['policy']:_tensor(saved['policy'][k],reference['policy'][k])
    _tensor(saved['alpha'],reference['alpha']);_tensor(saved['rng'],reference['rng']);torch.Generator().set_state(saved['rng'])
    for k,opt in zip(('critic','actor','temperature'),u._optimizers()):_optimizer(saved[k],opt,saved['counts'][k])
    u._restore(deepcopy(saved));u._finite_state();check(_same(saved,u._snapshot()),'Full network/Adam/Torch RNG restore differs')
    return dict(path=path.relative_to(C.ROOT).as_posix(),manifest_sha256=C.digest(path/'manifest.json'),arm=arm,batches=n,
        replay_rows=len(b.replay),episodes=len(b.refs),complete_state_verified=True,actor_sha256=u.fingerprints()['actor'])

binding=C.verify_binding(pins['binding_sha256'],with_runtime=True);run=C.HERE/'run'
ledger=C.Ledger.load(run/'ledger.json',pins['binding_sha256'],pins['authorization_sha256']);status=ledger.state['status']
check(status!='healthy' and ledger.state['active'] is None,'Run must be terminal before audit')
check(not (C.HERE/'stop_requested.json').exists(),'Worker stopping is uncertain; do not close as verified')
account=ledger.accounting();check(C.read(run/'accounting.json')==account,'Terminal accounting stale')
process=C.read(C.HERE/'process_exit.json');exit_record=C.read(C.HERE/'exit_classification.json')
if status!='failed':
    code=0 if status=='complete' else 20;check(process['returncode']==exit_record['returncode']==code,'Terminal returncode differs')
    check(exit_record['status']==status,'Exit/ledger status differs')
rows=C.read(run/'results.json') if (run/'results.json').exists() else []
finished=[x for x in ledger.state['attempts'] if x['status']=='finished'];check([x['result'] for x in finished]==rows,'Missing attempt/results')
analyses=[]
for attempt,row in zip(finished,rows):
    identity=attempt['identity'];p=C.ROOT/row['archive_path'];receipt=C.read(p.parent/'status.json')
    check(C.digest(p)==row['archive_sha256']==receipt['archive_sha256'],'Archive/receipt digest differs')
    raw=json.loads(gzip.decompress(p.read_bytes()));_audit_physics(raw);AuditedReplay(capacity=13000)._prepare(raw['transitions'])
    check(raw['fault'] is None and raw['fault_tail_transitions']==[] and raw['episode_id']==identity['id'] and raw['current_identity']==identity and
        raw['case']==identity['case'] and raw['seed']==C.scope()['seed'] and raw['qualification_sha256']==pins['binding_sha256'],'Raw identity/fault differs')
    facts=raw['guard_facts'];guard=bool(facts['contact_reasons'] or facts['motion_reasons'] or facts['invalid_reasons'])
    check(raw['optimizer_steps_start']==raw['optimizer_steps']==row['training_batches'],'In-episode optimizer boundary differs')
    online=identity['stage'].endswith('_online');check(raw['training_admitted'] is online,'Evaluation entered learning permission')
    committed=len(raw['transitions']) if online and not guard else 0
    check(receipt['committed']==committed and receipt['discarded']==len(raw['transitions'])-committed,'Publication credit differs')
    if not facts['motion_reasons'] and not facts['invalid_reasons'] and all(x=='FORCE_LIMIT' for x in facts['contact_reasons']):
        check(FORCE_ONLY.classify(raw)==receipt['learning_eligibility'],'Terminal labels/guard rule differs')
    actual=dict(**identity,completed=True,**episode_metrics(raw),guard_hit=guard,archive_path=row['archive_path'],archive_sha256=C.digest(p),training_batches=raw['optimizer_steps'])
    check(C.canonical(actual)==C.canonical(row),'Saved metrics differ from full raw trajectory')
    check(facts['checked_substeps']==10*len(raw['transitions']),'Full physical substep audit differs')
    guard_rows=[r for r in raw['transitions'] if any(any(g in e['reason'].split('+') for g in facts['contact_reasons']+facts['motion_reasons']) for e in r['events'])]
    analyses.append(dict(id=identity['id'],reason=raw['final_session']['reason'],guard_facts=facts,events=raw['events'],
        first_guard_s=guard_rows[0]['trace_row']['time_s'] if guard_rows else None,final_position_m=raw['transitions'][-1]['trace_row']['position_m'],
        policy_sha256=raw['policy_sha256'],optimizer_batches=raw['optimizer_steps']))
datasets={}
for arm,d in ledger.state['datasets'].items():
    p=run/('dataset_'+arm+'.json');check(C.digest(p)==d['manifest_sha256'],'Current learning qualification changed');m=C.read(p)
    check(m['arm']==arm and m['binding_sha256']==pins['binding_sha256'] and m['authorization_sha256']==pins['authorization_sha256'] and
        m['historical_bytes_modified'] is False and [r['id'] for r in m['references']]==d['ids'],'Current/historical admission differs')
    for ref,receipt in zip(m['references'],m['current_receipts']):
        path=C.ROOT/ref['path'];raw=json.loads(gzip.decompress(path.read_bytes()));old=C.read(path.parent/'status.json');R.source_permission(raw,old)
        check(C.digest(path)==ref['sha256']==receipt['archive_sha256'],'Qualified warmup digest differs')
        stamp=FORCE_ONLY.classify(raw);proof=audit_sampling(raw)
        check(receipt['learning_eligibility']==stamp and receipt['sampling_proof']==proof and receipt['committed']==len(raw['transitions']) and
            receipt['training_admitted'] is True and receipt['historical_training_admitted'] is False and receipt['historical_committed']==0,'Fresh receipt proof differs')
    datasets[arm]=dict(qualified_episodes=4,qualified_rows=sum(r['committed'] for r in m['current_receipts']),historical_published_rows=0,manifest_sha256=C.digest(p))
checkpoints=[audit_checkpoint(p,ledger) for p in sorted(run.glob('checkpoint_*')) if p.is_dir() and (p/'manifest.json').exists()]
for arm,d in datasets.items():
    arm_checkpoints=[x for x in checkpoints if x['arm']==arm]
    d['branch_replay_verified']=bool(arm_checkpoints)
    d['actual_warmup_replay_rows_verified']=d['qualified_rows'] if arm_checkpoints else 0
for e in analyses:
    if e['optimizer_batches']:
        matched=[x for x in checkpoints if x['arm']==e['id'][0] and x['batches']==e['optimizer_batches']]
        check(len(matched)==1 and matched[0]['actor_sha256']==e['policy_sha256'],'Triggering policy does not match preserved complete checkpoint')
    else:check(e['policy_sha256']==C.read(run/'origin.json')['fingerprints']['actor'],'Initial policy changed')
costs=[C.read(run/(name+'_costs.json')) for name in ('main','restore') if (run/(name+'_costs.json')).exists()]
totals={key:sum(r[key] for r in costs) for key in ('model_module_calls_attempted','optimizer_steps_attempted','policy_states_attempted','physical_substeps_attempted','substep_forwards_attempted')}
check(totals['physical_substeps_attempted']<=account['control_cycles_reserved']*10 and totals['model_module_calls_attempted']<=C.scope()['model_module_calls_cap'] and
    totals['optimizer_steps_attempted']<=3*account['formal_batches_attempted'],'Measured cost cap exceeded')
if status!='failed':
    check(totals['physical_substeps_attempted']==totals['substep_forwards_attempted']==account['control_cycles_confirmed']*10,'Complete physical cost differs')
    expected_optimizer=0
    for arm in ('A','C'):
        p=run/('history_'+arm+'.json')
        if p.exists():
            hist=C.read(p);check(len(hist)==ledger.state['updates'][arm]['completed'],'History/ledger batches differ');expected_optimizer+=len(hist)+2*sum(r['active_rows']>0 for r in hist)
    check(totals['optimizer_steps_attempted']==expected_optimizer,'Actual Adam calls differ from permitted batches')
candidate_passed=(ledger.state['updates']['C']['completed']==2500 and len(ledger.rows('C_final'))==4 and all(r['success'] for r in ledger.rows('C_final')) and
    len(ledger.rows('C_restored'))==4 and all(r['success'] for r in ledger.rows('C_restored')) and ledger.state['restoration_pin'] is not None)
if candidate_passed:
    proof=C.read(run/'restoration.json');check(C.digest(run/'restoration.json')==ledger.state['restoration_pin'] and proof['exact_full_learning_state'] and proof['exact_physical_replay'],'Restoration proof differs')
    check(proof['process_id']!=C.read(C.HERE/'claim.json')['pid'],'Restoration used same process')
    for a,b in zip(ledger.rows('C_final'),ledger.rows('C_restored')):
        x=json.loads(gzip.decompress((C.ROOT/a['archive_path']).read_bytes()));y=json.loads(gzip.decompress((C.ROOT/b['archive_path']).read_bytes()))
        check(all(_same(x[k],y[k]) for k in ('case','seed','outcome','transitions','guard_facts','events','stop_samples','stop_time','audit_end_time_s','final_session')),'Independent full trajectory differs')
if candidate_passed:judgement='limited_target_passed'
elif status=='failed':judgement='operational_verification_blocked'
elif len(ledger.rows('initial'))!=4 or not all(r['success'] for r in ledger.rows('initial')):judgement='baseline_verification_blocked'
else:judgement='method_not_resolved'
automation=Path('C:/Users/ok everything/.codex/automations/b-2/automation.toml').read_text(encoding='utf-8');check('status = "PAUSED"' in automation,'Automatic tracker resumed')
check(not any(calls.values()),'Offline audit performed new actual computation')
out=C.HERE/'result_analysis';out.mkdir(exist_ok=False)
assessment=dict(status=status,judgement=judgement,limited_candidate_target_passed=candidate_passed,comparison_complete=status=='complete',
    accounting=account,actual_costs=totals,completed_attempts=len(rows),success=sum(r['success'] for r in rows),rows=rows,episodes=analyses,datasets=datasets,checkpoints=checkpoints,
    unexecuted_attempts=C.attempts()[len(ledger.state['attempts']):],offline_actual_calls=calls,protocol_tests=binding['protocol_tests'],
    bound_inputs_preserved=len(binding['input_sha256']),automatic_tracking='PAUSED',retry_allowed=False,b2_complete=False,independent_test_used=False,
    audited_at=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(timespec='seconds'),
    result_input_sha256={p.relative_to(C.ROOT).as_posix():C.digest(p) for p in run.rglob('*') if p.is_file()})
with (out/'assessment.json').open('x',encoding='utf-8') as f:json.dump(assessment,f,ensure_ascii=False,allow_nan=False,indent=2)
print(json.dumps(dict(status=status,judgement=judgement,completed=len(rows),accounting=account,actual_costs=totals,offline_actual_calls=calls),ensure_ascii=False))
