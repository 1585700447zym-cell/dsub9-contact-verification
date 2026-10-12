"""Bind reviewed implementation and exact human-delegated bounded authority."""
import datetime,json,os,subprocess,sys,unittest
import night_contract as N

def main():
    N.verify_parent()
    if (N.HERE/'binding.json').exists() or (N.HERE/'authorization.json').exists():raise FileExistsError('Authority already exists')
    result=subprocess.run([sys.executable,'-X','utf8','-B',str(N.HERE/'test_protocol.py')],cwd=N.ROOT,capture_output=True,text=True,encoding='utf-8')
    (N.HERE/'final_protocol.txt').write_text(result.stdout+result.stderr,encoding='utf-8')
    if result.returncode:raise RuntimeError('Protocol not green')
    review=N.read(N.HERE/'review_assessment.json')
    if not review['ready'] or review['critical'] or review['important']:raise ValueError('Implementation review not resolved')
    required=['night_contract.py','frozen_reader.py','run_evaluation.py','deployment_rules.py','audit_result.py','prepare.py','test_protocol.py','report_result.py','final_protocol.txt','review.md','review_assessment.json']
    files={ (N.HERE/name).relative_to(N.ROOT).as_posix():N.digest(N.HERE/name) for name in required}
    plan=N.ROOT/'docs/superpowers/plans/2026-10-01-frozen-c2000-night-closeout.md';files[plan.relative_to(N.ROOT).as_posix()]=N.digest(plan)
    binding=dict(version='frozen_c2000_night_binding_v1',scope=N.scope(),configs={k:N.config(k) for k in ('base','small')},protocol_passed=True,inputs_sha256=files)
    N.write(N.HERE/'binding.json',binding);pin=N.digest(N.HERE/'binding.json')
    authority=dict(version='frozen_c2000_night_authority_v1',approved=True,binding_sha256=pin,scope=N.scope(),
        user_confirmation='接下来我要去休息了，由你制定计划并实施推进计划进行长途作业，直到这一阶段完成或者遇到难以解决的问题再停止，明早我会再进行审核结果和验收，你明白我的意思吗',
        interpretation='Delegated bounded current phase: frozen C2000 evaluation and conditional single smaller XY deployment screen; no new training; user reviews completed evidence in morning.')
    N.validate_authority(authority,pin);N.write(N.HERE/'authorization.json',authority);auth=N.digest(N.HERE/'authorization.json')
    N.write(N.HERE/'execution_pins.json',dict(binding_sha256=pin,authorization_sha256=auth));N.verify(pin,auth,'base')
    print(json.dumps(dict(binding_sha256=pin,authorization_sha256=auth,dynamic_cap=10,new_training=0),ensure_ascii=False))

if __name__=='__main__':main()
