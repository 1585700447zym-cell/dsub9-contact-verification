"""Seal final protocols/sources and already authorized 8/0 preflight scope."""
import datetime,json,os,sys
from pathlib import Path
import xml.etree.ElementTree as ET
from execution_contract import (HERE,ROOT,DESIGN,DESIGN_PIN,read,digest,verify_files,verify_parent,scope,config,
    validate_authorization,verify_binding)
os.environ['MPLCONFIGDIR']=str(ROOT/'tmp/learning_mpl_cache')
def save(name,record):
    with (HERE/name).open('x',encoding='utf-8') as f:
        json.dump(record,f,ensure_ascii=False,allow_nan=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
def main():
    if any((HERE/x).exists() for x in ('binding.json','authorization.json','started.json','run')):raise FileExistsError('Stage already sealed or attempted')
    tag=sys.argv[1];tests=read(HERE/(tag+'.json'));cases=list(ET.parse(HERE/(tag+'.xml')).getroot().iter('testcase'))
    if tests['exit_code'] or tests['failures'] or tests['errors'] or any(tests['actual_calls'].values()) or tests['tests']!=len(cases):
        raise ValueError('Complete clean protocols required')
    if not {'test_protocol','tests.learning.test_atomic_json','tests.learning.test_windows_parent','tests.learning.test_force_failure_rules'}<=set(x.attrib.get('classname','').rsplit('.',1)[0] for x in cases):
        # pytest gives module-only names to module functions, class-qualified to unittest.
        names=[x.attrib.get('classname','') for x in cases]
        if not all(any(required in x for x in names) for required in ('test_protocol','test_atomic_json','test_windows_parent','test_force_failure_rules')):
            raise ValueError('Missing related protocol module')
    review=read(HERE/'review_assessment.json')
    if review.get('ready') is not True or review.get('critical')!=0 or review.get('important')!=0:raise ValueError('Clean independent review required')
    verify_parent()
    from run_preflight import select_runtime
    select_runtime()
    from tools.validation.verify_residual_interface import qualified_runtime
    from tools.learning.runtime import active_package
    runtime=qualified_runtime(active_package())
    parent=read(DESIGN/'delivery_verification.json');inputs={}
    for key in ('input_sha256','source_sha256','artifact_sha256'):inputs.update(parent[key])
    for path in (DESIGN/'delivery_verification.json',ROOT/'deliverables/learning_chain/b2_actor_lr_execution_20260930/candidate.json',
        ROOT/'deliverables/learning_chain/b2_bounded_cycle_20260927/retry_01/driver.py'):
        inputs[path.relative_to(ROOT).as_posix()]=digest(path)
    for name in ('execution_contract.py','sampling_runtime.py','run_preflight.py','test_protocol.py','protocol_runner.py',
        'related_runner.py','seal_execution.py','README.md','review.md','review_assessment.json',tag+'.json',tag+'.xml'):
        path=HERE/name;inputs[path.relative_to(ROOT).as_posix()]=digest(path)
    verify_files(inputs)
    binding=dict(version='temporal_preflight_binding_v1',parent_design_sha256=DESIGN_PIN,scope=scope(),config=config(),
        protocol_passed=True,protocol_tests=tests['tests'],runtime=runtime,input_sha256=inputs)
    save('binding.json',binding);binding_pin=digest(HERE/'binding.json')
    auth=dict(version='temporal_preflight_authorization_v1',approved=True,user_confirmation='继续',
        confirmation_context='用户在下一修复方案具体交付后继续：完成新入口、协议和审查，执行最多8次配对预检，0训练/0网络前向，任何保护或故障停止余量，不重试；收口。',
        authorized_at=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(timespec='seconds'),
        binding_sha256=binding_pin,scope=scope())
    validate_authorization(auth,binding_pin);save('authorization.json',auth)
    save('execution_pins.json',dict(binding_sha256=binding_pin,authorization_sha256=digest(HERE/'authorization.json')))
    verify_binding(binding_pin,with_runtime=True)
    print(json.dumps(dict(status='sealed_for_authorized_preflight',tests=tests['tests'],**read(HERE/'execution_pins.json')),ensure_ascii=False))
if __name__=='__main__':main()
