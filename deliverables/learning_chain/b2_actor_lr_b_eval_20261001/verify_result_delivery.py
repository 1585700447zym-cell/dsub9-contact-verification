"""Seal audited result delivery and rolling-document snapshots; no experiment."""
import builtins,datetime,json,re,shutil
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];OUT=HERE/'result_analysis'
original=builtins.__import__
def guard(name,*args,**kwargs):
    if name.split('.')[0] in ('torch','mujoco','stable_baselines3'):
        raise RuntimeError('Delivery verification forbids model and physics imports')
    return original(name,*args,**kwargs)
builtins.__import__=guard
from evaluation_contract import read,digest,verify_binding,require_authorization,verify_files,PARENT,Ledger
def check(ok,message):
    if not ok:raise ValueError(message)
pins=read(HERE/'execution_pins.json')
binding=verify_binding(pins['binding_sha256'])
require_authorization(pins['binding_sha256'],pins['authorization_sha256'])
a=read(OUT/'assessment.json');verify_files(a['input_sha256'])
ledger=Ledger.load(HERE/'run/ledger.json',pins['binding_sha256'],pins['authorization_sha256'])
check(a['accounting']==ledger.accounting(),'Accounting differs from final ledger')
check(a['status']=='controlled_stop' and ledger.state['status']=='stopped','Terminal state differs')
check(a['completed_points']==2 and a['successful_points']==0 and len(a['unexecuted_points'])==2,'Outcome differs')
check(read(HERE/'exit_classification.json')['controlled_stop'] is True,'Not a controlled stop')
check((HERE/'fault.log').stat().st_size==0,'Fault log is not empty')
parent=read(PARENT/'run_analysis/delivery_verification.json')
verify_files(parent['results_sha256']);verify_files(parent['result_delivery_sha256'])
old=ROOT/'deliverables/learning_chain/b2_atomic_repaired_cycle_20260929'
sealed=read(old/'sealed_files.json');verify_files(sealed)
mapping=read(ROOT/'deliverables/learning_chain/b2_actor_lr_implementation_20260930/parent_source_snapshots.json')
sources=read(old/'candidate.json')['source_sha256']
for rel,pin in sources.items():check(digest(ROOT/mapping.get(rel,rel))==pin,'Old source changed: '+rel)
docs=[ROOT/'项目进度跟踪.md',ROOT/'项目交付总览.md',ROOT/'deliverables/monthly_progress/2026-10/月报素材_2026-10.md',ROOT/'项目当前入口.md']
for doc in docs[:3]:
    text=doc.read_text(encoding='utf-8')
    check('0/2' in text and 'B.2未完成' in text and 'result_analysis/结果说明.md' in text,'Rolling status missing: '+doc.name)
links=0
for doc in [OUT/'结果说明.md',*docs]:
    for target in re.findall(r'\]\(([^)]+)\)',doc.read_text(encoding='utf-8')):
        if not target or re.match(r'^[a-z]+://',target) or target.startswith('#'):continue
        target=target.split('#')[0].strip('<>')
        if not target:continue
        check((doc.parent/target).exists(),'Broken local link: '+str(doc)+' -> '+target);links+=1
check('status = "PAUSED"' in Path('C:/Users/ok everything/.codex/automations/b-2/automation.toml').read_text(encoding='utf-8'),'Tracking resumed')
snap=OUT/'document_snapshot';snap.mkdir(exist_ok=False)
snapshots={}
for doc in docs:
    dest=snap/doc.name;shutil.copyfile(doc,dest)
    check(digest(doc)==digest(dest),'Snapshot differs')
    snapshots[doc.relative_to(ROOT).as_posix()]=dest.relative_to(ROOT).as_posix()
result_files=[p for p in OUT.rglob('*') if p.is_file()]
result_files += [HERE/name for name in ('audit_result.py','plot_result.py','publish_startup.py','publish_result.py','verify_result_delivery.py','startup_assessment.json','exit_classification.json','process_exit.json','execution.log','fault.log','started.json','claim.json','process.json')]
record=dict(status='verified',verified_at=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(timespec='seconds'),
    **pins,experiment_status=a['status'],b2_complete=False,new_computation=0,
    bound_inputs=len(binding['inputs_sha256']),historical_sealed_files=len(sealed),historical_source_files=len(sources),
    accounting=a['accounting'],local_links_checked=links,rolling_document_snapshots=snapshots,
    results_sha256=a['input_sha256'],result_delivery_sha256={p.relative_to(ROOT).as_posix():digest(p) for p in result_files})
with (OUT/'delivery_verification.json').open('x',encoding='utf-8') as stream:
    json.dump(record,stream,ensure_ascii=False,allow_nan=False,indent=2);stream.write('\n')
print(json.dumps({k:v for k,v in record.items() if k not in ('results_sha256','result_delivery_sha256','rolling_document_snapshots')},ensure_ascii=False))
