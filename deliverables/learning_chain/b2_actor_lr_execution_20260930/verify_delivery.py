"""Verify pinned preparation and entry refusal without importing compute packages."""
import builtins
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
attempts=[];original_import=builtins.__import__
def guarded_import(name,*a,**k):
    if name.split('.')[0] in ('torch','mujoco','stable_baselines3'):
        attempts.append(name);raise AssertionError('Delivery entry probe cannot import compute packages')
    return original_import(name,*a,**k)
builtins.__import__=guarded_import
from tools.learning.actor_lr_contract import read,digest,verify_candidate,verify_files
from tools.validation.run_actor_lr_comparison import main
pin=read(HERE/'candidate_pin.json')['candidate_sha256'];candidate=verify_candidate(pin,check_runtime=False)
if main(['--candidate-sha256',pin,'--verify-only'])!=0:raise ValueError('Read-only verification failed')
try:main(['--candidate-sha256',pin])
except ValueError:authorization_refused=True
else:raise ValueError('Execution without explicit authorization was accepted')
if attempts or (HERE/'run').exists() or (HERE/'authorization.json').exists() or (HERE/'claim.json').exists() or (HERE/'started.json').exists():
    raise ValueError('Unexpected compute import, authorization, claim or execution')
verify_files(read(HERE/'protected_before.json'));verify_files(read(HERE/'parent_files.json'))
sources=read(HERE/'source_sha256.json')
if candidate['source_sha256']!=sources:raise ValueError('Source snapshot differs from candidate')
verify_files(sources)
paths=[ROOT/'项目进度跟踪.md',ROOT/'项目交付总览.md',ROOT/'deliverables/monthly_progress/2026-09/月报素材_2026-09.md']
for path in paths:
    if path.read_bytes()!=(HERE/'document_snapshot'/path.relative_to(ROOT)).read_bytes():raise ValueError('Rolling document snapshot changed')
links=0
for path in paths+[HERE/'README.md',HERE/'review.md']:
    for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)',path.read_text(encoding='utf-8')):
        if '://' in target or target.startswith('#'):continue
        rel=target.split('#')[0]
        if rel and not (path.parent/rel).resolve().exists():raise ValueError('Broken local link: '+target)
        links+=1
result=dict(status='execution_preparation_verified_not_authorized',date='2026-09-30',tests=read(HERE/'final_protocol_results.json')['tests'],
    candidate_sha256=pin,current_sources=296,execution_bound_inputs=len(sources),evidence_files=len(candidate['evidence_sha256']),
    compute_package_import_attempts=attempts,missing_authorization_refused_before_compute_import=True,
    protected_original_sources=286,protected_parent_artifacts=len(read(HERE/'parent_files.json')),old_sealed_files=4149,
    inherited_original_source_bytes=929,local_links=links,documents_maintained=3,real_validation_passed=False,
    a_learning_reproduced=False,policy_effect_validated=False,training_launched=False,old_unused_consumed=0,automatic_tracking='PAUSED',b2_complete=False,
    stage_file_sha256={p.relative_to(HERE).as_posix():digest(p) for p in HERE.rglob('*') if p.is_file() and not any(part.endswith('_work') for part in p.parts)})
with (HERE/'verification.json').open('x',encoding='utf-8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2);stream.write('\n')
print(json.dumps({k:v for k,v in result.items() if k!='stage_file_sha256'}))
