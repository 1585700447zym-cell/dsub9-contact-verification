"""Record the explicitly approved one-shot preflight without loading an engine."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(r'D:\dsub9项目计划\first_stage_sim\.worktrees\dsub9-v1-contact-validation')
OUT = ROOT / 'deliverables/learning_chain/b2_pose_scope_execution_20261008'
SOURCE = ROOT / 'deliverables/learning_chain/b2_pose_scope_preflight_20261008'
DOCS = ['项目当前入口.md', '项目进度跟踪.md', '项目交付总览.md', '研究推进计划_当前版.md',
        'deliverables/monthly_progress/2026-10/月报素材_2026-10.md',
        'docs/superpowers/plans/2026-10-08-b2-pose-scope-preflight.md']

def pin(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write_new(path, data):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write('\n')

def main():
    assert OUT == Path(__file__).resolve().parent
    assert not (OUT / 'grant.json').exists() and not (OUT / 'run').exists()
    assert pin(SOURCE / 'candidate_binding.json') == '9c15895cf6c8bac905715275c65dead6a8a48be617a3c197839077c7acf673c6'
    assert pin(SOURCE / 'delivery_manifest.json') == '178bf8cab98360b75148b4a587838e1a3493a4739576e4b713ef08a30f00a693'
    branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip()
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    assert branch == 'feature/dsub9-dynamic-actuator-v1'
    assert head == 'd2e7e4fa4ed0631d9dd1b7b98a121c1e46ea6406'
    status = subprocess.check_output(['git', '-c', 'core.quotepath=false', 'status', '--short'], cwd=ROOT)
    (OUT / 'git_status_before.txt').write_bytes(status)
    snapshots = {}
    for name in DOCS:
        target = OUT / 'before_documents' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write((ROOT / name).read_bytes())
        snapshots[name] = pin(target)
    request = json.loads((SOURCE / 'authorization_request.json').read_text(encoding='utf-8'))
    receipt = dict(stage_id='B2-SCOPE-03', user_date='2026-10-08',
        recorded_at=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
        latest_user_message='批准继续',
        approved_scope='9 次静态初始化全部通过后，按固定顺序执行最多 16 个动态预检；训练 0，不重试。',
        provenance='本对话上一阶段提出上述具体额度后，用户最新消息明确回复“批准继续”。',
        branch=branch, head=head, root=str(ROOT), request_sha256=pin(SOURCE / 'authorization_request.json'),
        implementation_manifest_sha256=pin(SOURCE / 'delivery_manifest.json'),
        binding_sha256=pin(SOURCE / 'candidate_binding.json'), before_documents=snapshots,
        cumulative_dynamic_before=208, automatic_tracking='PAUSED', old_budgets_reopened=False,
        training_admitted=False, retry_allowed=False)
    grant = dict(version='b2_pose_scope_grant_v1', status='OPEN', explicit_user_approval=True,
        authorization_text=receipt['provenance'] + '批准范围：' + receipt['approved_scope'],
        binding_sha256=request['binding_sha256'], proposal_sha256=request['proposal_sha256'],
        scope_key=request['scope_key'], limits=request['limits'], stage_id='B2-SCOPE-03',
        recorded_at=receipt['recorded_at'], automatic_tracking='PAUSED', training_admitted=False,
        retry_allowed=False)
    sys.path.insert(0, str(SOURCE))
    from scope_contract import proposal
    from execution_contract import validate_grant
    validate_grant(grant, pin(SOURCE / 'candidate_binding.json'), proposal())
    write_new(OUT / 'authorization_receipt.json', receipt)
    write_new(OUT / 'grant.json', grant)
    (OUT / 'grant.sha256').write_text(pin(OUT / 'grant.json') + '\n', encoding='ascii')
    assert not any(x.split('.')[0] in {'numpy', 'mujoco', 'torch', 'stable_baselines3'} for x in sys.modules)
    print(json.dumps(dict(status='REGISTERED_EXPLICIT_USER_APPROVAL', grant_sha256=pin(OUT / 'grant.json'),
        output=str(OUT / 'run'), limits=grant['limits']), ensure_ascii=False))

if __name__ == '__main__':
    main()
