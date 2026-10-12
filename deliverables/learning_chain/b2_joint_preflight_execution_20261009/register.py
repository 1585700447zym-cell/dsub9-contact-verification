"""Register the human-authorized fixed run; never starts the backend."""
from pathlib import Path
import datetime
import json
import re
import shutil
import subprocess
import sys
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
RUNNER=OUT.parent/'b2_joint_admission_preflight_20261009'
sys.path.insert(0,str(RUNNER))
from scope_contract import sha,read,canonical,proposal
from execution_contract import validate_grant,write
from run_preflight import check_binding
DOCS=['项目当前入口.md','项目进度跟踪.md','项目交付总览.md','研究推进计划_当前版.md','deliverables/monthly_progress/2026-10/月报素材_2026-10.md','AGENTS.md']

def main():
    if (OUT/'registration.json').exists() or (OUT/'run').exists() or (RUNNER/'claims').exists():raise PermissionError('Already registered/consumed; no retry')
    expected={'delivery_manifest.json':'914c2ead9cd87fe9e3a70e18e504bae36cbabfa6aa389839a8de875a694027fd',
        'candidate_binding.json':'be1e76e77db5d25ba8128a820bc8ab3e9e2c7c75a93c41a3d11884c272698fb3',
        'candidate.json':'1cde8986b548efb82ad971f3e47ad1c416b7ab5cd661f6fb7ee0881cbd10a986'}
    for n,pin in expected.items():
        if sha(RUNNER/n)!=pin:raise ValueError('Reviewed candidate differs: '+n)
    for rel,meta in read(RUNNER/'delivery_manifest.json')['files'].items():
        if sha(RUNNER/rel)!=meta['sha256']:raise ValueError('Sealed member differs: '+rel)
    c,b=check_binding();request=read(RUNNER/'authorization_request.json')
    grant=dict(version='b2_joint_preflight_grant_v1',status='OPEN',explicit_user_approval=True,
        binding_sha256=expected['candidate_binding.json'],proposal_sha256=expected['candidate.json'],
        scope_key=request['scope_key'],limits=request['limits'],
        authorization_text='2026-10-09，人类用户在上一轮明确交付“另行批准固定12次物理预检（8次动作、4次恢复，训练0、整体硬限6小时）”及具体申请后，回复“继续”。本次授权仅承接该固定申请；不授权训练、重试、变更阈值或重开旧预算。',
        human_message='继续',authorization_context='Direct human follow-up to the B2-SCOPE-09 final deliverable and fixed12 application',
        registered_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),stage_id='B2-SCOPE-10',
        cumulative_before=225,training_admitted=False,retry_allowed=False,automatic_tracking='PAUSED')
    validate_grant(grant,expected['candidate_binding.json'],c)
    write(OUT/'grant.json',grant)
    before={}
    for name in DOCS:
        p=OUT/'before_documents'/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,p);before[name]=sha(p)
    git=lambda *a:subprocess.check_output(['git',*a],cwd=ROOT)
    (OUT/'git_status_before.txt').write_bytes(git('status','--porcelain=v1'))
    reg=dict(stage_id='B2-SCOPE-10',status='REGISTERED_ONCE_NOT_YET_EXECUTED',grant_sha256=sha(OUT/'grant.json'),grant_validated=True,
        branch=git('branch','--show-current').decode().strip(),head=git('rev-parse','HEAD').decode().strip(),
        runner_pins=expected,sealed_runner_members=60,bound_inputs=len(b['files']),before_documents=before,
        limits=request['limits'],fixed_attempt_ids=[r['id'] for r in c['attempts']],cumulative_before=225,
        no_retry=True,training_admitted=False,automatic_tracking='PAUSED')
    write(OUT/'registration.json',reg)
    running={}
    for name in DOCS[:-1]:
        p=ROOT/name;t=p.read_text(encoding='utf-8')
        block='<!-- b2-scope-current -->\n**2026-10-09｜当前阶段B.2；任务：B2-SCOPE-10固定12项联合点物理预检，正在执行。** 用户在B2-SCOPE-09交付固定申请后回复“继续”，本轮新的一次性授权已登记。固定8次A/B动作＋4次R工程恢复、单独静态0、训练0；每回合14500周期／145000子步、1200秒，合计174000周期／1740000子步、整体6小时。\n\n本轮开始前实际累计动态225；执行中的已预留／完成数以新run/ledger.json为准，237仅为全部执行时的累计上限，不预记为已完成。运行／保护／审核失败关闭后续分配，无重试或补采。\n\n当前runner与旧封存校验通过；本轮物理结果仍在产生，不先宣称覆盖或验收。完整B.2/C未验收，训练未准入，自动跟踪PAUSED，旧预算关闭。沿用原工作区与全部未提交修改。以下历史下一项不代表当前授权。\n<!-- /b2-scope-current -->'
        t,n=re.subn(r'<!-- b2-scope-current -->.*?<!-- /b2-scope-current -->',lambda m:block,t,count=1,flags=re.S)
        assert n==1;p.write_text(t,encoding='utf-8');running[name]=sha(p)
    write(OUT/'running_document_update.json',dict(after_documents=running))
    (OUT/'progress.md').write_text('# B2-SCOPE-10 execution ledger\n\nSpec: sealed B2-SCOPE-09 candidate/authorization request.\nHuman authorization: 2026-10-09 direct “继续” following concrete fixed12 proposal. No new training.\nTask1: registration/source/snapshot checks complete; physical not started at registration.\nTask2: invoke the sealed runner once; retain every attempt; no rerun after closure.\nTask3: archive outcome/coverage/cost/claim evidence, update five rolling docs and six snapshots, verify/seal, then pause.\n',encoding='utf-8')
    print(canonical(dict(status='REGISTERED',grant_sha256=reg['grant_sha256'],binding_sha256=expected['candidate_binding.json'],output=str(OUT/'run'),physical_started=False)))
if __name__=='__main__':main()
