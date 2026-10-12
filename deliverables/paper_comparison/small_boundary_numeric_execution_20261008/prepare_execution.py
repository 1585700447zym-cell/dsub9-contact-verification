"""File-only explicit authorization registration; never imports torch."""
from pathlib import Path
import json,shutil,sys,time
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
KIT=OUT.parent/'small_boundary_numeric_gate_20261007'
sys.path.insert(0,str(KIT))
from numeric_contract import read,write,exclusive,sha,digest,verify_numeric_authorization,CLAIMS
from numeric_worker import verify_sources


def main():
    if (OUT/'authorization.json').exists() or (OUT/'run').exists() or (OUT/'attempt_registration.json').exists():
        raise FileExistsError('One explicit authorization; never prepare a second attempt')
    if sha(KIT/'delivery_manifest.json')!='51eef860885bcea78c4324149060014d8faac5ce1d8e760c0abc4a9ea68eb6e9':
        raise ValueError('PC13 seal changed')
    m=read(KIT/'delivery_manifest.json')
    for name,item in m['files'].items():
        if sha(KIT/name)!=item['sha256'] or (KIT/name).stat().st_size!=item['bytes']:raise ValueError('PC13 member changed: '+name)
    c=read(KIT/'numeric_candidate.json');verify_sources(c)
    grant=read(KIT/'authorization_request.json')
    grant.update(status='OPEN',explicit_user_authorized=True,authorization='批准继续',
        authorization_date='2026-10-08',authorization_timezone='Asia/Shanghai',
        authorization_evidence='Direct human reply to the immediately preceding 4-update/32-state/400-synthetic-row, physics/formal0 proposal',
        stage='PC-14',single_attempt=True)
    pin=digest(grant);binding=verify_numeric_authorization(c,grant,pin)
    if (CLAIMS/pin).exists():raise FileExistsError('Authorization already claimed')
    exclusive(OUT/'authorization.json',grant)
    write(OUT/'authorization_pin.json',dict(sha256=pin,binding=binding))
    shutil.copyfile(KIT/'numeric_candidate.json',OUT/'candidate_snapshot.json')
    shutil.copyfile(KIT/'source_bindings.json',OUT/'prior_source_bindings.json')
    write(OUT/'execution_registration.json',dict(stage='PC-14',user_date='2026-10-08',authorization_sha256=pin,
        candidate_sha256=digest(c),profile_sha256=c['profile_sha256'],kit_seal_sha256=sha(KIT/'delivery_manifest.json'),
        old_sealed_files=765,kit_sealed_files=33,shared_inputs=1057,runtime_file_pins=36,
        limits=c['limits'],future_synthetic_rows=400,physical_episodes=0,formal_updates=0,prior_dynamic=208,
        worker=str(KIT/'numeric_worker.py'),folder=str(OUT/'run'),claim=str(CLAIMS/pin)))
    docs=['项目当前入口.md','项目进度跟踪.md','项目交付总览.md','研究推进计划_当前版.md','deliverables/monthly_progress/2026-10/月报素材_2026-10.md']
    for name in docs:
        target=OUT/'before_documents'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
    exclusive(OUT/'attempt_registration.json',dict(authorization_sha256=pin,wall_timestamp=time.time(),status='ONE_EXECUTION_REGISTERED_NO_RETRY'))
    with (OUT/'progress.md').open('a',encoding='utf8') as f:
        f.write('\nTask preparation: complete — 798旧封存成员/1057输入/36runtime文件核验，授权/候选摘要绑定，原五份滚动资料快照保存。\n')
    print('AUTHORIZED SINGLE SYNTHETIC EXECUTION',pin,'max4/32 rows400 physics/formal0')


if __name__=='__main__':main()
