"""Freeze reviewed code, protocol evidence and this user's delegated budget."""
import json,sys
import paired_contract as C

def main():
    if (C.HERE/'binding.json').exists() or (C.HERE/'authorization.json').exists():raise FileExistsError('Execution binding already exists')
    C.verify_parent()
    tests=C.read(C.HERE/'protocol_result.json');review=C.read(C.HERE/'review_assessment.json')
    if tests.get('returncode')!=0 or not tests.get('all_passed') or not review.get('ready') or review.get('critical') or review.get('important'):raise ValueError('Green tests and resolved review required')
    C.verify_files(tests['tested_source_sha256'])
    from run_pair import select_runtime
    from tools.validation.verify_residual_interface import qualified_runtime
    from tools.learning.runtime import active_package
    select_runtime();runtime=qualified_runtime(active_package())
    names=[p.name for p in C.HERE.glob('*.py')]+['protocol_result.json','protocol_output.txt','review.md','review_assessment.json']
    inputs={(C.HERE/name).relative_to(C.ROOT).as_posix():C.digest(C.HERE/name) for name in names}
    inputs[C.PLAN.relative_to(C.ROOT).as_posix()]=C.digest(C.PLAN)
    binding=dict(version='paired_resume_binding_v1',parent_delivery_sha256=C.PARENT_PIN,scope=C.scope(),configs={a:C.config(a) for a in ('F','S')},
        runtime=runtime,protocol_passed=True,inputs_sha256=inputs)
    C.write(C.HERE/'binding.json',binding);pin=C.digest(C.HERE/'binding.json')
    authority=dict(version='paired_resume_authority_v1',approved=True,binding_sha256=pin,scope=C.scope(),
        user_confirmation='继续（在读取故障诊断与复用数据恢复方案汇报后）',
        interpretation='Execute the recovery plan: max18 newly registered dynamics and2500 updates per arm, requalify8 sealed warmups and reference4 sealedB2; both zero-reader gates before learning. Preserve failed parent and closed remainder; no independent test or automatic retry.')
    C.write(C.HERE/'authorization.json',authority);auth=C.digest(C.HERE/'authorization.json')
    C.write(C.HERE/'execution_pins.json',dict(binding_sha256=pin,authorization_sha256=auth));C.verify(pin,auth,with_runtime=True)
    print(json.dumps(dict(binding_sha256=pin,authorization_sha256=auth,dynamic_cap=18,training_batches_cap=5000),ensure_ascii=False))

if __name__=='__main__':main()
