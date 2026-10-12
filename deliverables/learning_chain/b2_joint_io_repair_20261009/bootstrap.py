"""Register an offline repair stage; retain all previous evidence and dirty files."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
OLD=OUT.parent/'b2_joint_sac_execution_20261009'
KIT=OUT.parent/'b2_joint_sac_preparation_20261009'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

if __name__=='__main__':
    if (OUT/'registration.json').exists():raise FileExistsError('Stage already registered')
    names=['AGENTS.md','项目当前入口.md','项目进度跟踪.md','研究推进计划_当前版.md','项目交付总览.md','deliverables/monthly_progress/2026-10/月报素材_2026-10.md']
    before={}
    for name in names:
        dst=OUT/'before_documents'/name;dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/name,dst);before[name]=sha(dst)
    for name in ('joint_contract.py','supervised.py','windows_job.py'):
        shutil.copyfile(KIT/name,OUT/name)
    git=lambda *args:subprocess.check_output(['git',*args],cwd=ROOT).decode('utf8')
    (OUT/'git_status_before.txt').write_text(git('status','--porcelain=v1'),encoding='utf8')
    record=dict(stage_id='B2-SCOPE-14',scope='offline_io_repair_and_recovery_evidence',
        branch=git('branch','--show-current').strip(),head=git('rev-parse','HEAD').strip(),
        before_documents=before,old_manifest_sha256=sha(OLD/'delivery_manifest.json'),
        base_sources={n:sha(KIT/n) for n in ('joint_contract.py','supervised.py','windows_job.py')},
        physics=0,learning=0,checkpoint_loads=0,restart_authorized=False,cumulative_dynamic=245)
    (OUT/'registration.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(record,ensure_ascii=False))
