"""One-time human grant registration; standard-library only, no physical work."""
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(r'D:\dsub9项目计划\first_stage_sim\.worktrees\dsub9-v1-contact-validation')
OUT = ROOT / 'deliverables/learning_chain/b2_rebound_execution_20261008'
RUNNER = ROOT / 'deliverables/learning_chain/b2_preflight_rebound_20261008'
DOCS = ['项目当前入口.md', '项目进度跟踪.md', '项目交付总览.md', '研究推进计划_当前版.md',
        'deliverables/monthly_progress/2026-10/月报素材_2026-10.md', 'AGENTS.md']
PINS = {'delivery_manifest.json': 'd373a6071a4967743b7d960b89bdb82cb2b366a85b49b7cdb933ecd416edc876',
        'candidate_binding.json': 'b7746e0cfaf29317c1ae692f6ed03c685d0d1a3398965c3fa36fc012b8ed3952',
        'candidate.json': '56b1af5518ddf81573995e31585873e1a46188dba88c2fe77a1f4982ca630d0e'}

def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''): h.update(block)
    return h.hexdigest()

def write_new(p, obj):
    with Path(p).open('x', encoding='utf-8', newline='\n') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2); f.write('\n')

def main():
    assert not (OUT/'grant.json').exists() and not (OUT/'run').exists(), 'Registration/output already exists'
    git = lambda *args: subprocess.check_output(['git', *args], cwd=ROOT)
    branch = git('branch', '--show-current').decode().strip()
    head = git('rev-parse', 'HEAD').decode().strip()
    assert branch == 'feature/dsub9-dynamic-actuator-v1'
    assert head == 'd2e7e4fa4ed0631d9dd1b7b98a121c1e46ea6406'
    for name, pin in PINS.items(): assert sha(RUNNER/name) == pin, name
    manifest = json.loads((RUNNER/'delivery_manifest.json').read_text(encoding='utf-8'))
    assert len(manifest['files']) == 61
    for name, row in manifest['files'].items():
        assert sha(RUNNER/name) == row['sha256'] and (RUNNER/name).stat().st_size == row['bytes'], name
    request = json.loads((RUNNER/'authorization_request.json').read_text(encoding='utf-8'))
    sys.path.insert(0, str(RUNNER))
    from execution_contract import validate_grant
    from scope_contract import proposal
    candidate = proposal()
    grant = dict(version='b2_pose_scope_grant_v1', status='OPEN', explicit_user_approval=True,
                 authorization_text='本会话最新人类消息原文：“批准继续”。承接上一轮已提交的具体新运行方案：9次无积分静态初始化全部通过后，8点按zero/script固定顺序最多16个动态回合；环境/复位各25次、训练/网络推理0、不重试、整轮监督硬限6小时；累计动态209至最多225。旧15回合继续关闭。',
                 binding_sha256=request['binding_sha256'], proposal_sha256=request['proposal_sha256'],
                 scope_key=request['scope_key'], limits=request['limits'],
                 stage_id='B2-SCOPE-06', registered_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),
                 user_message='批准继续', automatic_tracking='PAUSED', training_admitted=False,
                 old_budgets_reopened=False, retry_allowed=False, cumulative_before=209)
    validate_grant(grant, PINS['candidate_binding.json'], candidate)
    assert not any(k.split('.')[0] in {'numpy','mujoco','torch','stable_baselines3'} for k in sys.modules)
    snapshots = {}
    for name in DOCS:
        target = OUT/'before_documents'/name; target.parent.mkdir(parents=True, exist_ok=True)
        assert not target.exists(); shutil.copyfile(ROOT/name, target); snapshots[name] = sha(target)
    (OUT/'git_status_before.txt').write_bytes(git('-c','core.quotepath=false','status','--porcelain=v1'))
    (OUT/'git_status_before.z').write_bytes(git('status','--porcelain=v1','-z'))
    write_new(OUT/'grant.json', grant)
    pin = sha(OUT/'grant.json')
    write_new(OUT/'registration.json', dict(stage_id='B2-SCOPE-06', status='REGISTERED_ONCE_NOT_YET_EXECUTED',
              grant_sha256=pin, grant_validated=True, branch=branch, head=head, runner_pins=PINS,
              sealed_runner_members=61, before_documents=snapshots, limits=grant['limits'],
              user_message='批准继续', authorization_provenance=grant['authorization_text'],
              no_retries=True, no_training=True, cumulative_before=209))
    (OUT/'progress.md').write_text('# B2-SCOPE-06 执行记录\n\n2026-10-08：用户批准新9次静态＋最多16动态方案，登记新grant；使用封存B2-SCOPE-05程序一次执行。旧授权和未用15回合保持关闭，训练/推理0。执行前保存六份文档与Git状态；原分支/HEAD、61个封存程序成员保持。\n', encoding='utf-8')
    print(json.dumps(dict(status='REGISTERED_NOT_EXECUTED', grant_sha256=pin, runner_members=61,
                         output=str(OUT/'run'), cumulative_before=209), ensure_ascii=False))

if __name__ == '__main__': main()
