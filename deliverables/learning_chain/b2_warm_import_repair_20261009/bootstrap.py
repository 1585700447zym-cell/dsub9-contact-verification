"""Register SCOPE17 without altering any old sealed source or execution record."""
from pathlib import Path
import hashlib,json,shutil,subprocess
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
PREV=HERE.parent/'b2_warm_reconstruction_preparation_20261009';FAILED=HERE.parent/'b2_warm_reconstruction_execution_20261009'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
if __name__=='__main__':
    if (HERE/'registration.json').exists():raise FileExistsError('Already registered')
    names=['AGENTS.md','项目当前入口.md','项目进度跟踪.md','研究推进计划_当前版.md','项目交付总览.md','deliverables/monthly_progress/2026-10/月报素材_2026-10.md']
    before={}
    for name in names:
        p=HERE/'before_documents'/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,p);before[name]=sha(p)
    copies=['bounded_io.py','phase_deadline.py','supervised.py','windows_job.py','joint_contract.py','recovery_audit.py',
        'gate_contract.py','numeric_state.py','gate_worker.py','run_gate.py','prepare_candidate.py','input_spec.json',
        'run_suite.py','fixture_worker.py','fixture_orphan_lock.py']+[p.name for p in PREV.glob('test_*.py')]
    for name in copies:shutil.copyfile(PREV/name,HERE/name)
    git=lambda *a:subprocess.check_output(['git',*a],cwd=ROOT).decode('utf8')
    (HERE/'git_status_before.txt').write_text(git('status','--porcelain=v1'),encoding='utf8')
    record=dict(stage_id='B2-SCOPE-17',branch=git('branch','--show-current').strip(),head=git('rev-parse','HEAD').strip(),
        before_documents=before,copies={n:sha(PREV/n) for n in copies},previous_candidate_seal=sha(PREV/'delivery_manifest.json'),
        failure_seal=sha(FAILED/'delivery_manifest.json'),numeric_authorized=False,training_admitted=False,cumulative_dynamic=245)
    (HERE/'registration.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf8')
    print('New offline repair registered; old candidate and failed run preserved.')
