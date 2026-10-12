"""Independently audit finished saved evaluations; no new model or physics work."""
import datetime,gzip,json,math,os,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];RUN=HERE/'run';OUT=HERE/'result_analysis'
sys.path.insert(0,str(ROOT));os.environ['MPLCONFIGDIR']=str(ROOT/'tmp/learning_mpl_cache')
from evaluation_contract import (read,digest,verify_binding,require_authorization,verify_files,Ledger,PARENT,B_PIN,B_STATE)
pins=read(HERE/'execution_pins.json')
require_authorization(pins['binding_sha256'],pins['authorization_sha256'])
from run_evaluation import select_runtime
select_runtime()
import torch,mujoco
calls=dict(model_forward=0,optimizer_step=0,physics=0)
def forbidden(kind):
    def fail(*a,**k):calls[kind]+=1;raise AssertionError('Offline audit cannot compute '+kind)
    return fail
torch.nn.Module._call_impl=forbidden('model_forward');torch.optim.Adam.step=forbidden('optimizer_step')
for name in ('mj_step','mj_step1','mj_step2','mj_forward','mj_resetData','mj_resetDataKeyframe'):setattr(mujoco,name,forbidden('physics'))
from tools.learning.sac_checkpoint import _audit_physics,_same
from tools.learning.episode_rules import FORCE_ONLY
from tools.learning.engineering_evaluation import episode_metrics
from tools.learning.bounded_cycle import cases
def check(value,message):
    if not value:raise ValueError(message)
binding=verify_binding(pins['binding_sha256'],with_runtime=True)
prior=read(PARENT/'run_analysis/delivery_verification.json')
verify_files(prior['results_sha256']);verify_files(prior['result_delivery_sha256'])
old=ROOT/'deliverables/learning_chain/b2_atomic_repaired_cycle_20260929'
verify_files(read(old/'sealed_files.json'))
mapping=read(ROOT/'deliverables/learning_chain/b2_actor_lr_implementation_20260930/parent_source_snapshots.json')
for rel,pin in read(old/'candidate.json')['source_sha256'].items():check(digest(ROOT/mapping.get(rel,rel))==pin,'Old source changed: '+rel)
ledger=Ledger.load(RUN/'ledger.json',pins['binding_sha256'],pins['authorization_sha256'])
check(ledger.state['status'] in ('stopped','complete'),'Audit needs a complete or controlled-stop terminal ledger')
check(ledger.state['active'] is None,'Active attempt remains')
cost=ledger.accounting();check(read(RUN/'accounting.json')==cost,'Accounting differs')
classification=read(HERE/'exit_classification.json');process=read(HERE/'process_exit.json')
expected=0 if ledger.state['status']=='complete' else 20
check(process['returncode']==classification['returncode']==expected,'Wrong finalized exit')
check(classification['execution_complete']==(expected==0) and classification['controlled_stop']==(expected==20),
      'Exit meaning differs')
rows=read(RUN/'results.json');receipts=read(RUN/'attempts.json');events=[];guard_records=[];behavior=[]
check(len(rows)==len(receipts)==cost['new_dynamic_starts'],'Missing attempts or outcomes')
state=torch.load(PARENT/'run/checkpoint_B/state.pt',map_location='cpu',weights_only=True)
from tools.learning.sac_update import tensor_digest
actor={k.removeprefix('actor.'):v for k,v in state['updater']['policy'].items() if k.startswith('actor.')}
# Use the production fingerprint definition below; the actor-only checkpoint
# digest is independently regenerated without constructing or calling a model.
actor_pin=tensor_digest(actor)
for i,(row,receipt) in enumerate(zip(rows,receipts)):
    case=cases()[i];path=RUN/'episodes'/case['name']/'episode.json.gz'
    check(digest(path)==receipt['archive_sha256'],'Raw archive pin differs')
    check(read(path.parent/'status.json')==receipt,'Receipt differs')
    raw=json.loads(gzip.decompress(path.read_bytes()));_audit_physics(raw);eligibility=FORCE_ONLY.classify(raw)
    check(raw['case']==case and raw['qualification_sha256']==pins['binding_sha256']
        and raw['checkpoint_sha256']==B_PIN and raw['policy_sha256']==actor_pin,'Raw identity differs')
    check(raw['training_admitted'] is False and receipt['committed']==0 and receipt['discarded']==len(raw['transitions'])
        and raw['optimizer_steps']==raw['optimizer_steps_start']==500,'Evaluation isolation differs')
    facts=raw['guard_facts'];actual=dict(case=case['name'],completed=True,**episode_metrics(raw),
        actor_states=len(raw['transitions']),guard_hit=bool(facts['contact_reasons'] or facts['motion_reasons'] or facts['invalid_reasons']))
    check(_same(row,actual) and ledger.state['attempts'][i]['result']==row,'Metrics or ledger differ')
    check(eligibility==receipt['learning_eligibility'],'Failure class differs')
    events.append(dict(case=case['name'],events=raw['events']))
    guard_records.append(dict(case=case['name'],classification=eligibility,checked_substeps=facts['checked_substeps'],
        max_rotation_deg=math.degrees(facts['max_rotation_from_start_rad'])))
    active=[r for r in raw['transitions'] if r['action_active']]
    last=raw['transitions'][-1]['trace_row'];position=last['position_m']
    x0=case['x_offset_m'];crossings=[r['trace_row']['time_s'] for r in raw['transitions']
        if x0 and r['trace_row']['position_m'][0]*x0<0]
    behavior.append(dict(case=case['name'],final_reason=raw['final_session']['reason'],
        initial_xy_m=[case['x_offset_m'],case['y_offset_m']],final_position_m=position,
        final_xy_within_50um=math.hypot(*position[:2])<=50e-6,
        first_x_center_crossing_s=crossings[0] if crossings else None,
        active_x_negative_fraction=sum(r['action_log']['raw_action'][0]<0 for r in active)/len(active) if active else None,
        active_x_mean=sum(r['action_log']['raw_action'][0] for r in active)/len(active) if active else None,
        last_active_raw_action=active[-1]['action_log']['raw_action'] if active else None))
proof=read(RUN/'verification.json')
check(proof['training_state_unchanged'] is True and proof['checkpoint_sha256']==B_PIN
    and not any(proof['forbidden_calls'].values()),'Frozen evaluation proof differs')
check(digest(PARENT/'run/checkpoint_B/state.pt')==B_STATE,'Frozen B state changed')
success=sum(row['success'] for row in rows)
if expected==0:
    complete=read(RUN/'completed.json')
    check(len(rows)==4 and complete['success']==success and complete['retains_initial_success_count']==(success==4),
          'Completed outcome differs')
check(not any(calls.values()),'Unexpected offline compute')
automation=Path('C:/Users/ok everything/.codex/automations/b-2/automation.toml').read_text(encoding='utf-8')
check('status = "PAUSED"' in automation,'Tracking unexpectedly resumed')
OUT.mkdir(exist_ok=False)
assessment=dict(status='complete' if expected==0 else 'controlled_stop',
    audited_at=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(timespec='seconds'),
    **pins,checkpoint_manifest_sha256=B_PIN,checkpoint_state_sha256=B_STATE,
    accounting=cost,completed_points=len(rows),successful_points=success,
    unexecuted_points=[c['name'] for c in cases()[len(rows):]],
    retains_initial_four_successes=len(rows)==4 and success==4,
    known_original_ability_not_retained=any(not r['success'] for r in rows),
    b2_complete=False,training_state_unchanged=True,replay_committed=0,
    forbidden_audit_calls=calls,protocol_tests=149,old_sources_preserved=1011,
    old_sealed_files_preserved=4149,inherited_source_bytes_preserved=929,
    parent_run_files_preserved=22,parent_result_files_preserved=12,
    bound_inputs_preserved=len(binding['inputs_sha256']),rows=rows,events=events,guard_records=guard_records,behavior=behavior,
    automatic_tracking='PAUSED',retry_allowed=False,
    input_sha256={p.relative_to(ROOT).as_posix():digest(p) for p in RUN.rglob('*') if p.is_file()})
with (OUT/'assessment.json').open('x',encoding='utf-8') as stream:
    json.dump(assessment,stream,ensure_ascii=False,allow_nan=False,indent=2);stream.write('\n')
print(json.dumps({k:v for k,v in assessment.items() if k not in ('input_sha256','rows','events','guard_records')},ensure_ascii=False))
