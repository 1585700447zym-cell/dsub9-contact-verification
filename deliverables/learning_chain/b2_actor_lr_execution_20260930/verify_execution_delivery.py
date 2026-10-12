"""Check and seal result documents without importing any compute package."""
import builtins
import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent;OUT=HERE/'run_analysis'
sys.path.insert(0,str(ROOT));attempts=[];original=builtins.__import__
def guarded(name,*a,**k):
    if name.split('.')[0] in ('torch','mujoco','stable_baselines3'):
        attempts.append(name);raise AssertionError('Document delivery must not import compute packages')
    return original(name,*a,**k)
builtins.__import__=guarded
from tools.learning.actor_lr_contract import read,digest,verify_candidate,require_authorization,verify_files,OLD
pin=read(HERE/'candidate_pin.json')['candidate_sha256'];auth=read(HERE/'authorization_pin.json')['authorization_sha256']
candidate=verify_candidate(pin,check_runtime=False);require_authorization(pin,auth)
verify_files(read(HERE/'protected_before.json'));verify_files(read(HERE/'parent_files.json'))
verify_files(read(OLD/'sealed_files.json'))
for rel,value in read(HERE/'verification.json')['stage_file_sha256'].items():
    if digest(HERE/rel)!=value:raise ValueError('Preparation changed: '+rel)
audit=read(OUT/'execution_audit.json');verify_files(audit['audit_inputs_sha256'])
assessment=read(OUT/'assessment.json')
assert not assessment['b2_complete'] and not assessment['candidate_effect_verified']
assert audit['accounting']==read(HERE/'run/accounting.json')
assert not any(audit['forbidden_call_counts'].values()) and not attempts
paths=[ROOT/'项目进度跟踪.md',ROOT/'项目交付总览.md',ROOT/'deliverables/monthly_progress/2026-10/月报素材_2026-10.md',ROOT/'项目当前入口.md']
for path in paths[:3]:
    content=path.read_text(encoding='utf-8')
    assert '2026-10-01' in content and 'B.2未完成' in content and 'PAUSED' in content,path
    assert 'run_analysis/停止结果说明.md' in content,path
progress=paths[0].read_text(encoding='utf-8');current=progress.split('## 当前状态\n',1)[1].strip().split('\n\n',1)[0]
assert '已受控停止' in current and 'B动态未执行' in current
assert '| 6 普通残差SAC | 新授权1000批实际完成' in progress
assert '| 8 正式证据与展示 | 10月结果' in progress
links=0
for path in paths+[OUT/'停止结果说明.md',OUT/'独立结果审查.md']:
    for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)',path.read_text(encoding='utf-8')):
        if '://' in target or target.startswith('#'):continue
        rel=target.split('#')[0]
        if rel and not (path.parent/rel).resolve().exists():raise ValueError('Broken local link: '+target)
        links+=1
snapshot=OUT/'document_snapshot';snapshot.mkdir(exist_ok=False)
for path in paths:
    target=snapshot/path.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(path,target);assert path.read_bytes()==target.read_bytes()
branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()
assert branch=='feature/dsub9-dynamic-actuator-v1'
record=dict(status='controlled_stop_delivery_verified_effect_not_established',
    date=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(timespec='seconds'),
    workdir=str(ROOT),branch=branch,local_links=links,rolling_documents=3,entry_snapshot=1,
    real_validation_passed=True,a_learning_exact=True,formal_batches=1000,new_dynamic_starts=1,
    physical_by_branch=dict(A=1,B=0),unused_new_dynamic=7,old_unused_consumed=0,
    b2_complete=False,candidate_effect_verified=False,automatic_tracking='PAUSED',
    compute_package_import_attempts=attempts,offline_audit_compute_calls=audit['forbidden_call_counts'],
    current_bound_inputs=len(candidate['source_sha256']),old_sealed_files=4149,preparation_original_files=49,
    results_sha256={p.relative_to(ROOT).as_posix():digest(p) for p in (HERE/'run').rglob('*') if p.is_file()},
    result_delivery_sha256={p.relative_to(ROOT).as_posix():digest(p) for p in OUT.rglob('*') if p.is_file()},
    helper_sha256={p.name:digest(p) for p in HERE.glob('*.py')})
with (OUT/'delivery_verification.json').open('x',encoding='utf-8') as stream:
    json.dump(record,stream,ensure_ascii=False,indent=2);stream.write('\n')
print(json.dumps({k:v for k,v in record.items() if not k.endswith('_sha256')},ensure_ascii=False))
