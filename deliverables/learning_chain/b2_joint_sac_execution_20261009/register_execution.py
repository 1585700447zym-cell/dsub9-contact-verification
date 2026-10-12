"""Record the explicit human approval for the sealed one-shot candidate."""
from pathlib import Path
import datetime
import shutil
import subprocess
import sys
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
KIT=OUT.parent/'b2_joint_sac_preparation_20261009'
sys.path.insert(0,str(KIT))
from joint_contract import read,write,sha,digest
from execution import verify_grant,verify_sources
SEAL='f724bd676013239d4ac593ae154c40e8f6fd7b423f82fb47425af071e15d9d38'


def main():
    if (OUT/'registration.json').exists() or (OUT/'execution').exists() or (KIT/'future_claims').exists():raise PermissionError('Never register or execute this scope twice')
    if sha(KIT/'delivery_manifest.json')!=SEAL:raise ValueError('Reviewed candidate seal differs')
    members=read(KIT/'delivery_manifest.json')['files']
    for name,item in members.items():
        if sha(KIT/name)!=item['sha256']:raise ValueError('Reviewed candidate changed: '+name)
    verify_sources(read(KIT/'source_binding.json'))
    before={}
    for name in read(KIT/'registration.json')['before_documents']:
        target=OUT/'before_documents'/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/name,target);before[name]=sha(target)
    request=read(KIT/'authorization_request.json')
    request.update(status='OPEN',explicit_user_authorized=True,
        human_evidence='本会话人类原文：批准继续。承接上一轮具体申请：17个仿真回合、最多2000批更新、整体硬限6小时；先过零起点完整保存及独立恢复门，固定F0评价4/预热4/在线4/F2000评价4/恢复复现1。候选已列明辅助构造7/张量读取2/保存2，失败即停、不重试、不结转，旧额度不重开。')
    pin=digest(request);verify_grant(read(KIT/'candidate.json'),request,pin,sha(KIT/'source_binding.json'))
    write(OUT/'grant.json',request);write(OUT/'grant_pin.json',dict(sha256=pin))
    git=lambda *a:subprocess.check_output(['git',*a],cwd=ROOT).decode('utf-8')
    branch=git('branch','--show-current').strip();head=git('rev-parse','HEAD').strip()
    assert branch=='feature/dsub9-dynamic-actuator-v1' and head=='d2e7e4fa4ed0631d9dd1b7b98a121c1e46ea6406'
    (OUT/'git_status_before.txt').write_text(git('status','--porcelain=v1'),encoding='utf-8')
    write(OUT/'registration.json',dict(stage_id='B2-SCOPE-13',status='REGISTERED_ONCE_NOT_YET_EXECUTED',
        registered_at=datetime.datetime.now().astimezone().isoformat(),user_message='批准继续',grant_sha256=pin,
        grant_validated=True,before_documents=before,branch=branch,head=head,cumulative_before=237,
        runner_pins={n:sha(KIT/n) for n in ('delivery_manifest.json','candidate.json','source_binding.json')},
        sealed_runner_members=len(members),old_sealed_members=1869,bound_inputs=len(read(KIT/'source_binding.json')['files']),
        limits=request['limits'],no_retry=True,automatic_tracking='PAUSED',training_admitted=False))
    (OUT/'progress.md').write_text('# B2-SCOPE-13 执行记录\n\n当前阶段B.2第3项。新授权已登记；先验证零起点完整恢复，后按固定17回合执行。所有旧授权保持关闭。\n\n本次只执行已封存候选，不改其源码、不另建工作区。发生任何异常关闭本次余额，保留证据并收口，不自动重试。\n',encoding='utf-8')
    print('Registered one new grant '+pin+'; candidate47 and source2555 verified; execution not yet started.')


if __name__=='__main__':main()
