"""Register SCOPE15 offline preparation, preserving previous snapshots and sources."""
from pathlib import Path
import json,shutil,hashlib,subprocess
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
REPAIR=OUT.parent/'b2_joint_io_repair_20261009';RUN=OUT.parent/'b2_joint_sac_execution_20261009'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
if __name__=='__main__':
    if (OUT/'registration.json').exists():raise FileExistsError('Already registered')
    names=['AGENTS.md','项目当前入口.md','项目进度跟踪.md','研究推进计划_当前版.md','项目交付总览.md','deliverables/monthly_progress/2026-10/月报素材_2026-10.md']
    before={}
    for name in names:
        p=OUT/'before_documents'/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,p);before[name]=sha(p)
    copies=['bounded_io.py','phase_deadline.py','supervised.py','windows_job.py','joint_contract.py','recovery_audit.py',
        'test_io_repair.py','test_supervisor.py','fixture_worker.py','test_related_contract.py','test_recovery_audit.py','run_suite.py']
    for name in copies:shutil.copyfile(REPAIR/name,OUT/name)
    git=lambda *a:subprocess.check_output(['git',*a],cwd=ROOT).decode('utf8')
    (OUT/'git_status_before.txt').write_text(git('status','--porcelain=v1'),encoding='utf8')
    reg=dict(stage_id='B2-SCOPE-15',branch=git('branch','--show-current').strip(),head=git('rev-parse','HEAD').strip(),
        before_documents=before,prior_seal=sha(REPAIR/'delivery_manifest.json'),copies={n:sha(REPAIR/n) for n in copies},
        numeric_execution_authorized=False,training_admitted=False,cumulative_dynamic=245)
    (OUT/'registration.json').write_text(json.dumps(reg,ensure_ascii=False,indent=2),encoding='utf8')
    old=json.loads((RUN/'grant.json').read_text(encoding='utf8'))
    summary=json.loads((RUN/'execution_summary.json').read_text(encoding='utf8'))
    receipt=json.loads((RUN/'execution/run/chain/warmup_F50_J01/status.json').read_text(encoding='utf8'))
    configuration=json.loads((RUN/'execution/configuration.json').read_text(encoding='utf8'))
    spec=dict(version='b2_warm_reconstruction_inputs_v1',source_grant_sha256=reg['source_grant_sha256'] if 'source_grant_sha256' in reg else
        json.loads((RUN/'grant_pin.json').read_text(encoding='utf8'))['sha256'],
        zero_manifest=str(RUN/'execution/run/checkpoints/zero/manifest.json'),zero_state=str(RUN/'execution/run/checkpoints/zero/state.pt'),
        zero_manifest_sha256=sha(RUN/'execution/run/checkpoints/zero/manifest.json'),zero_state_sha256=sha(RUN/'execution/run/checkpoints/zero/state.pt'),
        source_closure=str(RUN/'execution/authorization_closure.json'),source_summary=str(RUN/'execution_summary.json'),
        probe_archive=str(RUN/'execution/run/zero_F50_J01.json.gz'),
        warmup=[dict(id='warmup_F50_J0'+str(i),archive=str(RUN/('execution/run/chain/warmup_F50_J0'+str(i)+'/episode.json.gz')),
            receipt=str(RUN/('execution/run/chain/warmup_F50_J0'+str(i)+'/status.json'))) for i in range(1,5)],
        actor_sha256=receipt['policy_sha256'],source_boundary='after_four_complete_warmup_publications_before_online_J01',
        expected_replay_rows=19300,expected_active_rows=14127,expected_warm_draws=388,source_cumulative_dynamic=245)
    (OUT/'input_spec.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2),encoding='utf8')
    print('SCOPE15 registered; no numeric runtime or old artifact modified.')
