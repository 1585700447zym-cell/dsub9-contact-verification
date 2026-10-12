"""Recompute saved preflight evidence; all new neural/physics/optimizer work blocked."""
from copy import deepcopy
import datetime,gzip,json,math,os,sys
from pathlib import Path
from execution_contract import (HERE,ROOT,Ledger,read,digest,write,canonical,attempts,verify_binding,require_authorization,verify_files)
os.environ['MPLCONFIGDIR']=str(ROOT/'tmp/learning_mpl_cache')
pins=read(HERE/'execution_pins.json');require_authorization(pins['binding_sha256'],pins['authorization_sha256'])
from run_preflight import select_runtime
select_runtime()
import torch,mujoco
calls=dict(model_forward=0,optimizer=0,physics=0)
def forbidden(kind):
    def fail(*a,**k):calls[kind]+=1;raise AssertionError('Offline audit forbids '+kind)
    return fail
torch.nn.Module._call_impl=forbidden('model_forward');torch.optim.Adam.step=forbidden('optimizer')
for name in ('mj_step','mj_step1','mj_step2','mj_forward','mj_resetData','mj_resetDataKeyframe'):setattr(mujoco,name,forbidden('physics'))
from sampling_runtime import audit_sampling
from tools.learning.engineering_evaluation import episode_metrics
from tools.learning.sac_checkpoint import _audit_physics
from tools.learning.episode_rules import FORCE_ONLY
from tools.learning.audited_replay import AuditedReplay

def check(value,message):
    if not value:raise ValueError(message)
def windows(rows,width,contact=False):
    out=[];block=[]
    for r in rows:
        if not r['action_active'] or (contact and r['trace_row']['contact_count']<=0):block=[];continue
        block.append(r)
        if len(block)==width:
            out.append(dict(request=[math.fsum(x['action'][j]*x['dt'] for x in block)/math.fsum(x['dt'] for x in block) for j in range(4)],
                effective=[math.fsum(x['action_log']['effective_command_delta'][j]*x['dt'] for x in block)/math.fsum(x['dt'] for x in block) for j in (0,1)],
                start_s=block[0]['trace_row']['time_s']-block[0]['dt'],end_s=block[-1]['trace_row']['time_s']))
            block=[]
    return out
def axis_stats(blocks,key,n,threshold):
    result=[]
    for j in range(n):
        values=[b[key][j] for b in blocks]
        result.append(dict(count=len(values),rms_mean=math.sqrt(math.fsum(v*v for v in values)/len(values)) if values else None,
            minimum=min(values) if values else None,maximum=max(values) if values else None,
            positive_threshold_count=sum(v>=threshold for v in values),negative_threshold_count=sum(v<=-threshold for v in values),
            absolute_threshold_fraction=sum(abs(v)>=threshold for v in values)/len(values) if values else None))
    return result

binding=verify_binding(pins['binding_sha256'],with_runtime=True)
run=HERE/'run';ledger=Ledger.load(run/'ledger.json',pins['binding_sha256'],pins['authorization_sha256'])
check(ledger.state['status'] in ('stopped','complete','failed') and ledger.state['active'] is None,'Unclosed ledger')
cost=ledger.accounting();check(read(run/'accounting.json')==cost,'Accounting differs')
process=read(HERE/'process_exit.json');exit_record=read(HERE/'exit_classification.json')
if ledger.state['status'] in ('complete','stopped'):
    code=0 if ledger.state['status']=='complete' else 20
    check(process['returncode']==exit_record['returncode']==code,'Exit meaning differs')
    check(exit_record['execution_complete']==(code==0) and exit_record['controlled_stop']==(code==20),'Exit classification differs')
physics=read(run/'physics_calls.json');check(not any(physics['forbidden_calls'].values()),'Unexpected learning call')
rows=read(run/'results.json') if (run/'results.json').exists() else []
receipts=read(run/'attempts.json') if (run/'attempts.json').exists() else []
finished=[x for x in ledger.state['attempts'] if x['status']=='finished']
check(len(rows)==len(finished),'Finished attempts missing')
analyses=[];pooled={'A':{10:[],50:[],200:[]},'C':{10:[],50:[],200:[]}};contact_c=[]
for i,row in enumerate(rows):
    identity=attempts()[i];path=run/'episodes'/identity['id']/'episode.json.gz';receipt=receipts[i]
    check(digest(path)==receipt['archive_sha256'] and read(path.parent/'status.json')==receipt,'Archive or receipt differs')
    raw=json.loads(gzip.decompress(path.read_bytes()));_audit_physics(raw);proof=audit_sampling(raw)
    check(canonical(raw['preflight_identity'])==canonical(identity) and raw['episode_id']==identity['id'] and
        canonical(raw['case'])==canonical(identity['case']) and raw['qualification_sha256']==pins['binding_sha256'],'Raw identity differs')
    check(raw['fault'] is None and not raw['fault_tail_transitions'] and raw['training_admitted'] is False and
        raw['optimizer_steps']==raw['optimizer_steps_start']==0 and receipt['committed']==0 and
        receipt['discarded']==len(raw['transitions']),'Isolation or fault differs')
    AuditedReplay(capacity=13000)._prepare(raw['transitions']);facts=raw['guard_facts']
    if not facts['motion_reasons'] and not facts['invalid_reasons'] and all(x=='FORCE_LIMIT' for x in facts['contact_reasons']):
        check(FORCE_ONLY.classify(raw)==receipt['rule_audit'],'Force/clear rule audit differs')
    actual=dict(**identity,completed=True,**episode_metrics(raw),draw_count=proof['draw_count'],model_forwards=0,training_batches=0,
        guard_hit=bool(facts['contact_reasons'] or facts['motion_reasons'] or facts['invalid_reasons']))
    check(canonical(actual)==canonical(row) and canonical(row)==canonical(finished[i]['result']),'Result metrics differ')
    check(facts['checked_substeps']==10*len(raw['transitions']),'Substep audit differs')
    data=raw['transitions'];last=data[-1]['trace_row'];first=next((x for x in data if x['trace_row']['contact_count']>0),None)
    window_stats={}
    for width in (10,50,200):
        blocks=windows(data,width);pooled[identity['arm']][width].extend(blocks)
        window_stats[str(width*.002)]=dict(count=len(blocks),axes=axis_stats(blocks,'request',4,.8))
    contact=windows(data,50,True)
    if identity['arm']=='C':contact_c.extend(contact)
    analyses.append(dict(id=identity['id'],arm=identity['arm'],hold_cycles=identity['hold_cycles'],cycles=len(data),
        draw_count=proof['draw_count'],sampling_proof=proof,guard_facts=facts,events=raw['events'],final_reason=raw['final_session']['reason'],
        first_saved_contact_s=None if first is None else first['trace_row']['time_s'],final_position_m=last['position_m'],
        final_xy_error_m=math.hypot(*last['position_m'][:2]),windows=window_stats,
        contact_active_100ms_windows=len(contact),contact_effective_axes=axis_stats(contact,'effective',2,1e-6),
        max_reference_lead_m=max(math.dist(x['trace_row']['position_m'],x['trace_row']['reference_qpos'][:3]) for x in data)))
pooled_stats={arm:{str(width*.002):dict(count=len(blocks),axes=axis_stats(blocks,'request',4,.8)) for width,blocks in by_width.items()} for arm,by_width in pooled.items()}
request_axes=pooled_stats['C']['0.1']['axes'];effective_axes=axis_stats(contact_c,'effective',2,1e-6)
all_eight_guard_clear=len(rows)==8 and ledger.state['status']=='complete' and all(not r['guard_hit'] and r['simulation_valid'] and r['physical_stopped'] for r in rows)
gates=dict(all_eight_valid_stopped_guard_clear=all_eight_guard_clear,
    coverage_evaluated=all_eight_guard_clear,request_bidirectional=all(x['positive_threshold_count'] and x['negative_threshold_count'] for x in request_axes),
    contact_effective_bidirectional=all(x['positive_threshold_count'] and x['negative_threshold_count'] for x in effective_axes),
    request_axes=request_axes,contact_effective_axes=effective_axes)
gates['candidate_collection_preflight_passed']=all_eight_guard_clear and gates['request_bidirectional'] and gates['contact_effective_bidirectional']
check(cost['control_cycles_confirmed']*10<=physics['total_substeps_attempted']<=cost['control_cycles_reserved']*10,'Total physical accounting differs')
if ledger.state['status']!='failed':check(cost['control_cycles_confirmed']*10==physics['total_substeps_attempted']==physics['substep_forwards_attempted'],'Actual complete physical calls differ')
check(not any(calls.values()),'Offline audit computed')
automation=Path('C:/Users/ok everything/.codex/automations/b-2/automation.toml').read_text(encoding='utf-8')
check('status = "PAUSED"' in automation,'Tracking resumed')
out=HERE/'result_analysis';out.mkdir(exist_ok=False)
assessment=dict(status=ledger.state['status'],audited_at=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(timespec='seconds'),
    accounting=cost,physics_calls=physics,completed_attempts=len(rows),success=sum(r['success'] for r in rows),
    unexecuted_attempts=attempts()[cost['new_dynamic_starts']:],gates=gates,rows=rows,episodes=analyses,pooled_request_windows=pooled_stats,
    b2_complete=False,training_admitted=False,automatic_tracking='PAUSED',retry_allowed=False,offline_actual_calls=calls,
    bound_inputs_preserved=len(binding['input_sha256']),protocol_tests=binding['protocol_tests'],
    input_sha256={p.relative_to(ROOT).as_posix():digest(p) for p in run.rglob('*') if p.is_file()})
with (out/'assessment.json').open('x',encoding='utf-8') as f:json.dump(assessment,f,ensure_ascii=False,allow_nan=False,indent=2)
print(json.dumps(dict(status=assessment['status'],completed=len(rows),success=assessment['success'],accounting=cost,
    gates={k:v for k,v in gates.items() if not k.endswith('axes')},offline_actual_calls=calls),ensure_ascii=False))
