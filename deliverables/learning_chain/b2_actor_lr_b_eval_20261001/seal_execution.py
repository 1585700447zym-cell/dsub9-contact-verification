"""Seal tested adapter and the user's approved four-point, zero-training scope."""
import datetime
import json
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT));os.environ['MPLCONFIGDIR']=str(ROOT/'tmp/learning_mpl_cache')
from evaluation_contract import (read,digest,verify_files,verify_candidate,scope,verify_binding,
    PARENT,PARENT_PIN,PARENT_AUTH,B_PIN,B_STATE,validate_authorization)
from tools.learning.admission import verify_test_report
def check(condition,message):
    if not condition:raise ValueError(message)
if any((HERE/name).exists() for name in ('binding.json','authorization.json','run','started.json')):
    raise FileExistsError('This sealing or execution was already attempted')
def save(name,record):
    with (HERE/name).open('x',encoding='utf-8') as stream:
        json.dump(record,stream,ensure_ascii=False,allow_nan=False,indent=2);stream.write('\n')
tests=read(HERE/'related_green_results.json')
check(tests['exit_code']==tests['failures']==tests['errors']==0 and not any(tests['forbidden_call_counts'].values()),'Protocol tests did not pass')
cases=list(ET.parse(HERE/'related_green.xml').getroot().iter('testcase'))
verified=verify_test_report(HERE/'related_green.xml',minimum=149,required_modules={
    'test_protocol','test_actor_lr_runner','test_windows_parent','test_atomic_json','test_force_failure_rules',
    'test_actor_lr_engine','test_actor_lr_execution_contract','test_actor_lr_execution_gates'})
check(verified['passed']==tests['tests']==len(cases),'Protocol receipt and full report differ')
candidate=verify_candidate(PARENT_PIN,check_runtime=False)
previous=read(PARENT/'run_analysis/delivery_verification.json')
verify_files(previous['results_sha256']);verify_files(previous['result_delivery_sha256'])
verify_files(read(ROOT/'deliverables/learning_chain/b2_atomic_repaired_cycle_20260929/sealed_files.json'))
from run_evaluation import select_runtime
select_runtime()
import torch,mujoco
calls=dict(model_forward=0,optimizer_step=0,physics=0)
def forbidden(kind):
    def fail(*a,**k):calls[kind]+=1;raise AssertionError('Preflight must not compute '+kind)
    return fail
torch.nn.Module._call_impl=forbidden('model_forward');torch.optim.Adam.step=forbidden('optimizer_step')
for name in ('mj_step','mj_step1','mj_step2','mj_forward','mj_resetData','mj_resetDataKeyframe'):setattr(mujoco,name,forbidden('physics'))
from tools.learning.actor_lr_engine import read_origin,load_checkpoint
from tools.learning.sac_checkpoint import _same
origin,plan=read_origin()
state,updater=load_checkpoint(PARENT/'run/checkpoint_B',B_PIN,origin,plan,'B',PARENT_PIN,PARENT_AUTH)
check(_same(updater._snapshot(),state['updater']) and updater.counts['critic']==500,'B complete restoration differs')
check(not any(calls.values()),'Preflight attempted real computation')
save('restoration_preflight.json',dict(status='complete_frozen_B_restoration_verified',manifest_sha256=B_PIN,
    state_sha256=B_STATE,optimizer_counts=updater.counts,complete_state_equal=True,forbidden_call_counts=calls))
inputs=dict(previous['results_sha256']);inputs.update(previous['result_delivery_sha256'])
inputs.update({p.relative_to(ROOT).as_posix():digest(p) for p in HERE.glob('*') if p.is_file()})
for p in (PARENT/'run_analysis/delivery_verification.json',PARENT/'authorization.json',PARENT/'candidate.json'):
    inputs[p.relative_to(ROOT).as_posix()]=digest(p)
binding=dict(version='frozen_B_evaluation_binding_v1',scope=scope(),config=candidate['configs']['B'],
    parent_candidate_sha256=PARENT_PIN,parent_authorization_sha256=PARENT_AUTH,protocol_passed=True,
    protocol_tests=tests['tests'],inputs_sha256=inputs)
save('binding.json',binding);binding_pin=digest(HERE/'binding.json')
authorization=dict(version='frozen_B_evaluation_authorization_v1',approved=True,user_confirmation='继续',
    confirmation_context='用户确认：完成独立入口适配和协议验证后直接执行冻结B最多4个原开发点，训练0，保护后停止余点，故障不重试，并收口。',
    authorized_at=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(timespec='seconds'),
    binding_sha256=binding_pin,scope=scope())
validate_authorization(authorization,binding_pin);save('authorization.json',authorization)
save('execution_pins.json',dict(binding_sha256=binding_pin,authorization_sha256=digest(HERE/'authorization.json')))
verify_binding(binding_pin,with_runtime=True)
print(json.dumps(dict(status='ready_under_user_authorized_scope',**read(HERE/'execution_pins.json'),
    tests=tests['tests'],restoration_verified=True,forbidden_call_counts=calls),ensure_ascii=False))
