"""Verify sealed sources/results, preserve rolling-document snapshots and seal closeout."""
import datetime,json,re
from pathlib import Path
from execution_contract import HERE,ROOT,DESIGN,read,digest,verify_binding,verify_files,require_authorization,canonical
def check(x,message):
    if not x:raise ValueError(message)
def save(path,r):
    with path.open('x',encoding='utf-8') as f:json.dump(r,f,ensure_ascii=False,allow_nan=False,indent=2);f.write('\n')
pins=read(HERE/'execution_pins.json');require_authorization(pins['binding_sha256'],pins['authorization_sha256'])
binding=verify_binding(pins['binding_sha256'])
out=HERE/'result_analysis';a=read(out/'assessment.json');verify_files(a['input_sha256'])
old=ROOT/'deliverables/learning_chain/b2_atomic_repaired_cycle_20260929'
old_files=read(old/'sealed_files.json');verify_files(old_files)
mapping=read(ROOT/'deliverables/learning_chain/b2_actor_lr_implementation_20260930/parent_source_snapshots.json')
inherited=read(old/'candidate.json')['source_sha256']
for rel,pin in inherited.items():check(digest(ROOT/mapping.get(rel,rel))==pin,'Inherited bytes changed: '+rel)
parent=ROOT/'deliverables/learning_chain/b2_actor_lr_b_eval_20261001/result_analysis'
for name in ('delivery_verification.json','final_review_verification.json'):
    r=read(parent/name)
    for key in ('sha256','results_sha256','result_delivery_sha256'):
        if key in r:verify_files(r[key])
review=read(out/'review_assessment.json')
check(review.get('ready') is True and review.get('critical')==review.get('important')==0,'Result review not clean')
snap=out/'document_snapshot';snap.mkdir(exist_ok=False)
documents=[ROOT/'项目进度跟踪.md',ROOT/'项目交付总览.md',ROOT/'项目当前入口.md',ROOT/'deliverables/monthly_progress/2026-10/月报素材_2026-10.md']
links=0
for path in documents:
    (snap/path.name).write_bytes(path.read_bytes())
    text=path.read_text(encoding='utf-8')
    check('100ms预热配对预检已收口' in text,'Latest outcome not integrated: '+path.name)
    for target in re.findall(r'\]\(([^)]+)\)',text):
        target=target.strip('<>')
        if re.match(r'^(?:https?://|codex:|mailto:|#)',target):continue
        target=target.split('#',1)[0]
        if not target:continue
        candidate=(path.parent/target).resolve()
        check(candidate.exists(),'Broken local link: '+path.name+' → '+target);links+=1
files={}
for directory in (HERE/'run',out):
    for p in directory.rglob('*'):
        if p.is_file():files[p.relative_to(ROOT).as_posix()]=digest(p)
for name in ('binding.json','authorization.json','execution_pins.json','process_exit.json','exit_classification.json','started.json',
    'process.json','claim.json','execution.log','fault.log','audit_result.py','plot_result.py','publish_result.py','publish_startup.py',
    'refine_result_docs.py','fix_review_docs.py','verify_preservation.py','finalize_delivery.py','progress.md'):
    p=HERE/name;files[p.relative_to(ROOT).as_posix()]=digest(p)
check(a['offline_actual_calls']==dict(model_forward=0,optimizer=0,physics=0),'Unexpected offline compute')
verification=dict(status='bounded_preflight_closeout_verified',time=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(timespec='seconds'),
    actual_status=a['status'],accounting=a['accounting'],completed_attempts=a['completed_attempts'],success=a['success'],
    candidate_collection_preflight_passed=a['gates']['candidate_collection_preflight_passed'],training_admitted=False,b2_complete=False,
    automatic_tracking='PAUSED',related_protocols=binding['protocol_tests'],bound_inputs_preserved=len(binding['input_sha256']),
    historical_sealed_files_preserved=len(old_files),inherited_source_bytes_preserved=len(inherited),local_links_checked=links,
    result_review=review,sha256=files)
verify_files(files);save(out/'delivery_verification.json',verification)
print(json.dumps({k:v for k,v in verification.items() if k not in ('sha256','result_review')},ensure_ascii=False))
