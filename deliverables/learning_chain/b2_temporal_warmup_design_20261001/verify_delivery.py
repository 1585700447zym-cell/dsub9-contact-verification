"""Read-only preservation checks plus a new immutable preparation seal."""
import builtins,datetime,hashlib,json,re,shutil
from pathlib import Path
original=builtins.__import__
def guard(name,*a,**k):
    if name.split('.')[0] in ('torch','mujoco','stable_baselines3','tools'):
        raise RuntimeError('Preparation seal may not load computation runtimes')
    return original(name,*a,**k)
builtins.__import__=guard
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def check(value,message):
    if not value:raise ValueError(message)
def verify(mapping):
    for rel,pin in mapping.items():check(sha(ROOT/rel)==pin,'Changed input: '+rel)
old=ROOT/'deliverables/learning_chain/b2_atomic_repaired_cycle_20260929'
b=ROOT/'deliverables/learning_chain/b2_actor_lr_b_eval_20261001'
ab=ROOT/'deliverables/learning_chain/b2_actor_lr_execution_20260930'
protected=read(ab/'candidate.json')['source_sha256'];verify(protected)
sealed=read(old/'sealed_files.json');verify(sealed)
mapping=read(ROOT/'deliverables/learning_chain/b2_actor_lr_implementation_20260930/parent_source_snapshots.json')
sources=read(old/'candidate.json')['source_sha256']
for rel,pin in sources.items():check(sha(ROOT/mapping.get(rel,rel))==pin,'Inherited source bytes changed')
for previous in (ab/'run_analysis/delivery_verification.json',b/'result_analysis/delivery_verification.json'):
    item=read(previous);verify(item['results_sha256']);verify(item['result_delivery_sha256'])
verify(read(b/'result_analysis/final_review_verification.json')['sha256'])
analysis=read(HERE/'archive_analysis.json');verify(analysis['input_sha256'])
check(len(analysis['input_sha256'])==8 and analysis['opposite_x_initial_observations_equal'],'Archive conclusions differ')
tests=read(HERE/'final_green_protocol.json')
check(tests['tests']==18 and tests['failures']==tests['errors']==tests['skipped']==0 and not tests['forbidden_imports'],'Protocol did not pass')
check(read(HERE/'final_red_protocol.json')['failures']==1 and read(HERE/'review_red_protocol.json')['failures']==2,'Missing recovery counterexamples')
p=read(HERE/'proposal.json')
check(p['execution_admitted'] is p['training_admitted'] is False and p['candidate_hold_cycles']==50,'Preparation scope changed')
check(all(p[k]==0 for k in ('actual_new_dynamic','actual_new_model_forwards','actual_new_training_batches','old_unused_consumed')),'Unexpected computation claim')
check(read(b/'run/accounting.json')['cumulative_dynamic']==60,'Prior cumulative accounting differs')
check('status = "PAUSED"' in Path('C:/Users/ok everything/.codex/automations/b-2/automation.toml').read_text(encoding='utf-8'),'Tracking resumed')
docs=[ROOT/'项目进度跟踪.md',ROOT/'项目交付总览.md',ROOT/'deliverables/monthly_progress/2026-10/月报素材_2026-10.md',ROOT/'项目当前入口.md']
link_count=0
for doc in [HERE/'修复方案.md',*docs]:
    text=doc.read_text(encoding='utf-8')
    for link in re.findall(r'\]\(([^)]+)\)',text):
        if not link or re.match(r'^[a-z]+://',link) or link.startswith('#'):continue
        link=link.split('#')[0].strip('<>')
        if link:check((doc.parent/link).exists(),'Broken link: '+str(doc)+' -> '+link);link_count+=1
for doc in docs[:3]:
    text=doc.read_text(encoding='utf-8')
    check('18' in text and 'b2_temporal_warmup_design_20261001/修复方案.md' in text and 'B.2未完成' in text,'Current preparation status missing')
check((HERE/'review.md').exists(),'Independent review not recorded')
snap=HERE/'document_snapshot';snap.mkdir(exist_ok=False)
for doc in docs:shutil.copyfile(doc,snap/doc.name);check(sha(doc)==sha(snap/doc.name),'Document snapshot differs')
result=dict(status='preparation_verified',time=datetime.datetime.now().astimezone().isoformat(timespec='seconds'),
    protocol_passed=18,archive_episodes=8,new_model_forwards=0,new_physics=0,new_updates=0,
    execution_admitted=False,training_admitted=False,production_entry_connected=False,b2_complete=False,
    cumulative_dynamic=60,automatic_tracking='PAUSED',bound_source_files_preserved=len(protected),
    historical_sealed_files_preserved=len(sealed),inherited_source_files_preserved=len(sources),
    local_links_checked=link_count,input_sha256=analysis['input_sha256'],
    source_sha256=protected,
    artifact_sha256={x.relative_to(ROOT).as_posix():sha(x) for x in HERE.rglob('*') if x.is_file()})
with (HERE/'delivery_verification.json').open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
print(json.dumps({k:v for k,v in result.items() if not k.endswith('_sha256')},ensure_ascii=False))
