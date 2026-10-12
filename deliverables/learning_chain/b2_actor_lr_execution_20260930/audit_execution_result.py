"""Read saved evidence only; forbid every new forward, Adam and physics call."""
import datetime
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
RUN=HERE/'run';OUT=HERE/'run_analysis'
sys.path.insert(0,str(ROOT));os.environ['MPLCONFIGDIR']=str(ROOT/'tmp/learning_mpl_cache')
from tools.validation.run_actor_lr_comparison import select_qualified_runtime
select_qualified_runtime()
import torch,mujoco
calls=dict(model_forward=0,optimizer_step=0,physics=0)
def forbidden(kind):
    def refuse(*a,**k):
        calls[kind]+=1
        raise AssertionError('Read-only result audit cannot compute: '+kind)
    return refuse
torch.nn.Module._call_impl=forbidden('model_forward');torch.optim.Adam.step=forbidden('optimizer_step')
for name in ('mj_step','mj_step1','mj_step2','mj_forward','mj_resetData','mj_resetDataKeyframe'):
    setattr(mujoco,name,forbidden('physics'))
from tools.learning.actor_lr_contract import read,digest,verify_candidate,require_authorization,verify_files,ORIGIN,OLD
from tools.learning.actor_lr_budget import ComparisonLedger
from tools.learning.actor_lr_engine import reproduction_fields_equal
from tools.learning.actor_lr_origin import read_pinned_state
from tools.learning.sac_checkpoint import _same,_audit_physics
from tools.learning.episode_rules import FORCE_ONLY
from tools.learning.engineering_evaluation import episode_metrics
def check(condition,message):
    if not condition:raise ValueError(message)
pin=read(HERE/'candidate_pin.json')['candidate_sha256']
auth=read(HERE/'authorization_pin.json')['authorization_sha256']
candidate=verify_candidate(pin);require_authorization(pin,auth)
verify_files(read(HERE/'protected_before.json'));verify_files(read(HERE/'parent_files.json'))
sealed=read(OLD/'sealed_files.json');verify_files(sealed)
mapping=read(ROOT/'deliverables/learning_chain/b2_actor_lr_implementation_20260930/parent_source_snapshots.json')
old_sources=read(OLD/'candidate.json')['source_sha256']
for rel,value in old_sources.items():check(digest(ROOT/mapping.get(rel,rel))==value,'Original source changed: '+rel)
preparation=read(HERE/'verification.json')['stage_file_sha256']
for rel,value in preparation.items():check(digest(HERE/rel)==value,'Preparation evidence changed: '+rel)
ledger=ComparisonLedger.load(RUN/'ledger.json',pin,auth);accounting=ledger.accounting()
check(accounting==read(RUN/'accounting.json'),'Accounting differs from validated ledger')
check(ledger.state['status']==ledger.state['phase']=='stopped' and ledger.state['active'] is None,
      'Closed stopped ledger required')
check(ledger.state['stop_reason']=='evaluation_guard','Wrong stop reason')
check(accounting['formal']==dict(A=500,B=500) and accounting['new_dynamic_starts']==1,
      'Unexpected actual compute budget')
check(all(r['status']=='finished' for r in ledger.state['attempts']),'Unfinished attempt')
classification=read(HERE/'exit_classification.json')
check(classification['controlled_stop'] is True and classification['returncode']==20 and
      classification['execution_complete'] is False and classification['accounting']==accounting,
      'Controlled stop classification differs')
for folder in (HERE,RUN/'eval_process_A'):
    check(read(folder/'process_exit.json')['returncode']==20,'Worker returncode differs')
check(not any((RUN/name).exists() for name in ('evaluation_B','eval_process_B','failure.json','completed.json','supervision_uncertain.json')),
      'Unexpected post-stop work or failure')
for gate,name in (('real_validation','real_validation.json'),('a_reproduced','a_reproduction.json'),('diagnostics','diagnostics.json')):
    check(digest(RUN/name)==ledger.state['gates'][gate],'Gate pin differs: '+gate)
frozen=read(RUN/'frozen.json');states={}
for role in ('A','B'):
    folder=RUN/frozen[role]['path'];manifest=read(folder/'manifest.json')
    check(digest(folder/'manifest.json')==frozen[role]['sha256']==ledger.state['gates']['evaluation_checkpoints'][role],
          'Frozen manifest differs')
    check(digest(folder/'state.pt')==manifest['state_sha256'],'Frozen state differs')
    states[role]=torch.load(folder/'state.pt',map_location='cpu',weights_only=True)
    check(states[role]['budget']['completed']==500,'Wrong checkpoint batch count')
historical=read_pinned_state(OLD/'run/training/checkpoints/train_03',read(RUN/'a_reproduction.json')['historical_manifest_sha256'])
check(reproduction_fields_equal(states['A'],historical),'Independent A reproduction differs')
check(_same(states['A']['replay'],states['B']['replay']) and _same(states['A']['archives'],states['B']['archives'])
      and _same(states['A']['rng'],states['B']['rng']),'Branch data or random streams differ')
folder=RUN/'evaluation_A';rows=read(folder/'results.json');attempts=read(folder/'attempts.json')
check(len(rows)==len(attempts)==1,'Wrong physical count')
receipt=attempts[0];episode=folder/'episodes/x_pos_100/episode.json.gz'
check(digest(episode)==receipt['archive_sha256'],'Archive digest differs')
check(read(episode.parent/'status.json')==receipt,'Publication receipt differs')
raw=json.loads(gzip.decompress(episode.read_bytes()));_audit_physics(raw)
eligibility=FORCE_ONLY.classify(raw)
check(eligibility==receipt['learning_eligibility']==dict(version='force_only_v1',kind='force_failure'),
      'Independent force-only classification differs')
metrics=episode_metrics(raw)
check(_same(rows[0],dict(case='x_pos_100',completed=True,**metrics,guard_hit=True)),
      'Recomputed physical metrics differ')
check(raw['training_admitted'] is False and receipt['committed']==0 and receipt['discarded']==6287 and
      raw['optimizer_steps']==raw['optimizer_steps_start']==500,'Evaluation learning isolation differs')
check(read(folder/'verification.json')==dict(training_state_unchanged=True,all_points_completed=False),
      'Evaluation verification differs')
physical=[r for r in ledger.state['attempts'] if r['kind']=='physical']
check(len(physical)==1 and physical[0]['result']==rows[0] and physical[0]['branch']=='A','Physical ledger differs')
summary=read(OUT/'distribution_summary.json')
check(summary['diagnostics_sha256']==digest(RUN/'diagnostics.json') and summary['states_per_role']==256,
      'Distribution source differs')
diag=read(RUN/'diagnostics.json')
for role in ('initial','A','B'):
    mu=diag['parameters'][role]['mean']
    for axis in range(4):
        actual=math.fsum(math.tanh(r[axis]) for r in mu)/256
        check(math.isclose(actual,summary['roles'][role]['per_axis'][axis]['deterministic_mean'],abs_tol=1e-14),
              'Saved distribution deterministic summary differs')
automation=Path('C:/Users/ok everything/.codex/automations/b-2/automation.toml').read_text(encoding='utf-8')
check('status = "PAUSED"' in automation,'Automatic tracking not paused')
check(not any(calls.values()),'Unexpected compute call')
result=dict(status='controlled_stop_evidence_verified',date=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(timespec='seconds'),
    candidate_sha256=pin,authorization_sha256=auth,accounting=accounting,unused_new_dynamic=7,
    physical_by_branch=dict(A=1,B=0),a_learning_reproduced_independently=True,
    checkpoint_states_pinned=True,branch_data_and_rng_equal=True,evaluation_training_state_unchanged=True,
    physical_metrics=metrics,force_only_classification=eligibility,checked_substeps=raw['guard_facts']['checked_substeps'],
    max_rotation_deg=math.degrees(raw['guard_facts']['max_rotation_from_start_rad']),events=raw['events'],
    b_physical_effect='not_evaluated',candidate_retains_initial_ability='not_established',b2_complete=False,
    current_bound_inputs=len(candidate['source_sha256']),protected_original_sources=286,
    protected_origin_artifacts=45,protected_preparation_files=len(preparation),protected_old_sealed_files=len(sealed),
    protected_inherited_source_bytes=len(old_sources),forbidden_call_counts=calls,automatic_tracking='PAUSED',
    audit_inputs_sha256={p.relative_to(ROOT).as_posix():digest(p) for p in RUN.rglob('*') if p.is_file()})
with (OUT/'execution_audit.json').open('x',encoding='utf-8') as stream:
    json.dump(result,stream,ensure_ascii=False,allow_nan=False,indent=2);stream.write('\n')
print(json.dumps({k:v for k,v in result.items() if k not in ('audit_inputs_sha256','events')},ensure_ascii=False))
