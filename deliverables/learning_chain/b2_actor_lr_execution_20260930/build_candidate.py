"""Seal protocol preparation only. Never approve or execute real computation."""
import hashlib
import json
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT));os.environ['PYTHONDONTWRITEBYTECODE']='1'
os.environ['MPLCONFIGDIR']=str(ROOT/'tmp/learning_mpl_cache')
from tools.learning.actor_lr_contract import (execution_config,compute_budget,source_inventory,verify_files,
    ORIGIN,ORIGIN_PIN,OLD,digest,read,verify_candidate)
from tools.learning.admission import verify_test_report


def check(condition,message):
    if not condition:raise ValueError(message)


def save(name,value):
    with (HERE/name).open('x',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False,allow_nan=False,indent=2);stream.write('\n')


result=read(HERE/'final_protocol_results.json')
check(result['exit_code']==result['failures']==result['errors']==0 and not any(result['forbidden_call_counts'].values()),'Monitored protocol tests did not pass')
modules={row.split('::')[0].split('.')[-1] for row in result['test_ids']}
report=verify_test_report(HERE/'final_protocol.xml',required_modules=modules,minimum=result['tests'])
check(report['sha256']==result['report_sha256'] and report['passed']==result['tests'],'Test report receipt differs')
observed=[c.get('classname')+'::'+c.get('name') for c in ET.parse(HERE/'final_protocol.xml').getroot().iter('testcase')]
check(observed==result['test_ids'],'Exact test identities differ')
check(not (HERE/'authorization.json').exists() and not (HERE/'run').exists(),'Execution already authorized or started')
verify_files(read(HERE/'protected_before.json'));verify_files(read(HERE/'parent_files.json'))
verify_files(read(OLD/'sealed_files.json'))
check(digest(ORIGIN/'manifest.json')==ORIGIN_PIN,'Origin pin differs')
mapping=read(ROOT/'deliverables/learning_chain/b2_actor_lr_implementation_20260930/parent_source_snapshots.json')
for rel,pin in read(OLD/'candidate.json')['source_sha256'].items():check(digest(ROOT/mapping.get(rel,rel))==pin,'Inherited original bytes differ: '+rel)
for branch in ('A','B'):save(f'config_{branch}.json',execution_config(branch))
inventory=source_inventory();save('source_sha256.json',inventory)
# Select the already frozen repaired runtime; import alone cannot run physics.
from tools.learning.runtime import select_runtime,active_package,verify_runtime
repaired=ROOT/'deliverables/learning_chain/b2_repaired_cycle_v2_20260928'
select_runtime(repaired/'runtime.json',expected_digest=read(repaired/'admission.json')['runtime_record_sha256'])
verify_runtime(active_package())
import torch,mujoco
calls=dict(model_forward=0,optimizer_step=0,physics=0)
def forbidden(kind):
    def refuse(*a,**k):calls[kind]+=1;raise AssertionError('Candidate sealing must not compute: '+kind)
    return refuse
torch.nn.Module._call_impl=forbidden('model_forward');torch.optim.Adam.step=forbidden('optimizer_step')
for name in ('mj_step','mj_step1','mj_step2','mj_forward','mj_resetData','mj_resetDataKeyframe'):setattr(mujoco,name,forbidden('physics'))
from tools.validation.verify_residual_interface import qualified_runtime
from tools.learning.actor_lr_engine import read_origin
state,plan=read_origin()
check(state['replay']['size']==22766 and state['budget']['completed']==0 and len(plan['batches'])==500,'Common origin is not zero-update fixed data')
evidence={p.relative_to(ROOT).as_posix():digest(p) for p in HERE.glob('*')
    if p.is_file() and p.name not in ('source_sha256.json','config_A.json','config_B.json')}
evidence.update(read(ORIGIN/'manifest.json')['archived_inputs_sha256'])
evidence.update({p.relative_to(ROOT).as_posix():digest(p) for p in ORIGIN.glob('*') if p.is_file()})
diag=ROOT/'deliverables/learning_chain/b2_actor_lr_implementation_20260930/diagnostic_states.json'
evidence[diag.relative_to(ROOT).as_posix()]=digest(diag)
evidence[(repaired/'runtime.json').relative_to(ROOT).as_posix()]=digest(repaired/'runtime.json')
for p in (HERE/'document_snapshot').rglob('*'):
    if p.is_file():evidence[p.relative_to(ROOT).as_posix()]=digest(p)
record=dict(version='actor_lr_comparison_candidate_v1',synthetic_only=False,protocol_preparation_passed=True,
    real_validation_required=True,user_authorization_required=True,origin_manifest_sha256=ORIGIN_PIN,
    configs={b:execution_config(b) for b in ('A','B')},budget=compute_budget(),source_sha256=inventory,
    evidence_sha256=evidence,runtime=qualified_runtime(active_package()),
    real_validation_passed=False,a_learning_reproduced=False,policy_effect_validated=False,b2_complete=False)
save('candidate.json',record);pin=digest(HERE/'candidate.json');verify_candidate(pin)
save('authorization_request.json',dict(version='actor_lr_user_authorization_v1',approved=False,
    candidate_sha256=pin,scope='validation_and_conditional_ab',user_confirmation='',budget=compute_budget()))
save('candidate_pin.json',dict(candidate_sha256=pin,origin_manifest_sha256=ORIGIN_PIN))
save('preflight.json',dict(status='protocol_preparation_verified_not_execution_authorized',tests=result['tests'],
    monitored_actual_calls=calls,source_files=len(inventory),evidence_files=len(evidence),candidate_sha256=pin,
    old_unused_consumed=0,automatic_tracking='PAUSED',training_launched=False,real_validation_passed=False,
    a_learning_reproduced=False,policy_effect_validated=False,b2_complete=False))
check(not any(calls.values()),'Unexpected computation during candidate sealing')
print(json.dumps(dict(candidate_sha256=pin,source_files=len(inventory),evidence_files=len(evidence),actual_calls=calls)))
