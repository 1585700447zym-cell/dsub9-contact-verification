"""Register the authorized offline continuation preparation; no scientific imports."""
import hashlib, json, shutil, subprocess
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
PREP = OUT.parent / 'b2_warm_import_repair_20261009'
RESTORE = OUT.parent / 'b2_warm_restore_execution_20261009'
OLD = OUT.parent / 'b2_joint_sac_execution_20261009'

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''): h.update(b)
    return h.hexdigest()

def read(path): return json.loads(Path(path).read_bytes())
def write(path, value): Path(path).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2), encoding='utf8')

if __name__ == '__main__':
    if (OUT / 'registration.json').exists(): raise FileExistsError('Preserve existing preparation')
    assert read(RESTORE / 'authorization_closure.json')['status'] == 'CLOSED_COMPLETE'
    before = {}
    names = ['AGENTS.md', '项目当前入口.md', '项目进度跟踪.md', '研究推进计划_当前版.md', '项目交付总览.md', 'deliverables/monthly_progress/2026-10/月报素材_2026-10.md']
    for name in names:
        dst = OUT / 'before_documents' / name; dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, dst); before[name] = sha(dst)
    git = lambda *a: subprocess.check_output(['git', *a], cwd=ROOT).decode('utf8')
    write(OUT / 'registration.json', dict(stage_id='B2-SCOPE-19', scope='offline_trainable_continuation_candidate',
          branch=git('branch', '--show-current').strip(), head=git('rev-parse', 'HEAD').strip(), before_documents=before,
          previous_restore_seal=sha(RESTORE / 'delivery_manifest.json'), cumulative_dynamic=245,
          physics=0, formal_updates=0, checkpoint_loads=0, training_admitted=False, human_request='继续：承接已说明的离线续训入口及匹配评价准备'))
    (OUT / 'git_status_before.txt').write_text(git('status', '--porcelain=v1'), encoding='utf8')
    spec = read(PREP / 'input_spec.json')
    spec.update(version='b2_continuation_inputs_v1', restoration_folder=str(RESTORE), restoration_seal=sha(RESTORE / 'delivery_manifest.json'),
                restoration_manifest_sha256=sha(RESTORE / 'checkpoint/manifest.json'),
                restoration_state_sha256=sha(RESTORE / 'checkpoint/state.pt'),
                restoration_state_digest=read(RESTORE / 'checkpoint/manifest.json')['state_digest'],
                legacy_config_sha256=read(OLD / 'execution/grant.json')['learning_config_sha256'] if 'learning_config_sha256' in read(OLD / 'execution/grant.json') else read(OUT.parent / 'b2_joint_sac_preparation_20261009/candidate.json')['learning_config_sha256'])
    for item in spec['warmup']: item['archive_sha256'] = sha(item['archive'])
    spec['baseline'] = [dict(id='zero_F50_J0' + str(i), archive=str(OLD / 'execution/run' / ('zero_F50_J0' + str(i) + '.json.gz'))) for i in range(1, 5)]
    for item in spec['baseline']: item['archive_sha256'] = sha(item['archive'])
    write(OUT / 'input_spec.json', spec)
    print('Registered offline preparation; six before snapshots preserved.')
