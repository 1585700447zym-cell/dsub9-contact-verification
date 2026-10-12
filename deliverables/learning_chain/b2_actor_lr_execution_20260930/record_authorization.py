"""Record the human's explicit approval of the sealed comparison; no compute."""
import builtins
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
original_import=builtins.__import__
def no_compute(name,*a,**k):
    if name.split('.')[0] in ('torch','mujoco','stable_baselines3'):raise AssertionError('Authorization record must not compute')
    return original_import(name,*a,**k)
builtins.__import__=no_compute
from tools.learning.actor_lr_contract import read,digest,verify_candidate,validate_authorization,require_authorization
pin=read(HERE/'candidate_pin.json')['candidate_sha256'];verify_candidate(pin,check_runtime=False)
if pin!='79a9bd0084f871e2ab6c6b24ff96ac69a772aa0e9e53003205866a31c11d2fba':raise ValueError('Human-approved candidate differs')
record=read(HERE/'authorization_request.json')
record.update(approved=True,user_confirmation='用户于2026-09-30回复“批准”，明确批准前一条所列新候选及16合成事务/128测试状态/768诊断状态/1000正式批/8动态上限；A复现不符或评价保护即停。',
    authorized_at='2026-09-30T22:31:34+08:00',approval_source='current_thread_human_reply_批准')
validate_authorization(record,pin)
if any((HERE/name).exists() for name in ('run','started.json','claim.json','authorization.json')):raise ValueError('Authorization or execution already exists; no overwrite/retry')
with (HERE/'authorization.json').open('x',encoding='utf-8') as stream:
    json.dump(record,stream,ensure_ascii=False,allow_nan=False,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
authorization_pin=digest(HERE/'authorization.json');require_authorization(pin,authorization_pin)
with (HERE/'authorization_pin.json').open('x',encoding='utf-8') as stream:
    json.dump(dict(candidate_sha256=pin,authorization_sha256=authorization_pin),stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
print(json.dumps(dict(candidate_sha256=pin,authorization_sha256=authorization_pin,scope=record['scope'])))
