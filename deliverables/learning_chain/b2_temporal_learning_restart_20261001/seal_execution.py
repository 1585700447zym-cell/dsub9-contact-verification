"""Bind reviewed sources and explicit current do-to-terminal authorization."""
import datetime,json,os,sys
from pathlib import Path
import xml.etree.ElementTree as ET
import validation_contract as C
def save(name,record):
    with (C.HERE/name).open('x',encoding='utf-8') as f:json.dump(record,f,ensure_ascii=False,allow_nan=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
def main():
    if any((C.HERE/x).exists() for x in ('binding.json','authorization.json','started.json','run')):raise FileExistsError('Stage already sealed/attempted')
    tag=sys.argv[1];tests=C.read(C.HERE/(tag+'.json'));cases=list(ET.parse(C.HERE/(tag+'.xml')).getroot().iter('testcase'))
    if tests['exit_code'] or tests['failures'] or tests['errors'] or any(tests['actual_calls'].values()) or tests['tests']!=len(cases):raise ValueError('Full clean protocol suite required')
    for module in ('test_protocol','test_atomic_json','test_windows_parent','test_force_failure_rules','test_boundary_targets','test_audited_replay','test_admitted_collection','test_actor_lr_engine'):
        if not any(module in x.attrib.get('classname','') for x in cases):raise ValueError('Missing related protocol module: '+module)
    review=C.read(C.HERE/'review_assessment.json')
    if review.get('ready') is not True or review.get('critical')!=0 or review.get('important')!=0:raise ValueError('Independent review blockers unresolved')
    C.verify_parent()
    from run_validation import select_runtime
    select_runtime()
    from tools.validation.verify_residual_interface import qualified_runtime,all_sources
    from tools.learning.runtime import active_package
    from tools.learning.actor_lr_contract import ORIGIN
    inputs=all_sources();inputs.update(C.read(C.PREFLIGHT/'binding.json')['input_sha256']);inputs.update(C.read(C.PREFLIGHT/'result_analysis/delivery_verification.json')['sha256'])
    for path in [C.PREFLIGHT/'binding.json',C.PREFLIGHT/'result_analysis/delivery_verification.json',ORIGIN/'manifest.json',ORIGIN/'state.pt',ORIGIN/'draw_plan.json.gz',ORIGIN/'source_sha256.json',C.ROOT/'deliverables/learning_chain/b2_bounded_cycle_20260927/retry_01/driver.py']:
        inputs[path.relative_to(C.ROOT).as_posix()]=C.digest(path)
    inputs.update(C.read(ORIGIN/'manifest.json')['archived_inputs_sha256']);inputs.update(C.read(ORIGIN/'source_sha256.json'))
    for parent in (C.FAILED/'result_analysis/delivery_verification.json',C.FIX/'delivery_verification.json'):
        inputs[parent.relative_to(C.ROOT).as_posix()]=C.digest(parent);inputs.update(C.read(parent)['sha256'])
    inputs.update(C.read(C.FAILED/'binding.json')['input_sha256'])
    for name in ('validation_contract.py','learning_runtime.py','run_validation.py','verify_zero_checkpoint.py','fault_evidence.py','audit_result.py','plot_result.py','update_documents.py','test_protocol.py','protocol_runner.py','related_runner.py','seal_execution.py','验证方案.md','review.md','review_assessment.json',tag+'.json',tag+'.xml'):
        path=C.HERE/name;inputs[path.relative_to(C.ROOT).as_posix()]=C.digest(path)
    C.verify_files(inputs)
    binding=dict(version='temporal_learning_binding_v1',parent_preflight_sha256=C.PREFLIGHT_PIN,scope=C.scope(),configs={a:C.config(a) for a in ('A','C')},protocol_passed=True,protocol_tests=tests['tests'],runtime=qualified_runtime(active_package()),input_sha256=inputs)
    save('binding.json',binding);pin=C.digest(C.HERE/'binding.json')
    auth=dict(version='temporal_learning_authorization_v1',approved=True,binding_sha256=pin,scope=C.scope(),
        user_confirmation='继续',
        confirmation_context='用户在保存修复交付及C500丢失/需新起点说明后要求继续，延续直接做到验证结束的授权；新起点零更新、新版本真实存取门、新24动态/5000批。此前累计72动态与失败500批保留，累计动态上限96/本方法正式批5500；原轮余量关闭不结转，任何保护或故障不重试。',
        authorized_at=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(timespec='seconds'))
    C.validate_authorization(auth,pin);save('authorization.json',auth);save('execution_pins.json',dict(binding_sha256=pin,authorization_sha256=C.digest(C.HERE/'authorization.json')))
    C.verify_binding(pin,with_runtime=True);print(json.dumps(dict(status='sealed',tests=tests['tests'],**C.read(C.HERE/'execution_pins.json'))))
if __name__=='__main__':main()
