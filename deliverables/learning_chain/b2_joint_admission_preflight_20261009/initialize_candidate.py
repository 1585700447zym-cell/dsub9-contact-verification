"""One-time local preparation; no environment imports, grant, or execution."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
OLD=OUT.parent/'b2_preflight_rebound_20261008'
DESIGN=OUT.parent/'b2_joint_admission_design_20261009'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def main():
    if (OUT/'registration.json').exists():raise PermissionError('Already initialized')
    docs=['AGENTS.md','项目当前入口.md','项目进度跟踪.md','项目交付总览.md','研究推进计划_当前版.md','deliverables/monthly_progress/2026-10/月报素材_2026-10.md']
    before={}
    for name in docs:
        dst=OUT/'before_documents'/name;dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/name,dst);before[name]=sha(dst)
    (OUT/'git_status_before.txt').write_bytes(subprocess.check_output(['git','status','--porcelain=v1'],cwd=ROOT))
    c=json.loads((DESIGN/'admission_proposal.json').read_text(encoding='utf-8'))
    old=json.loads((OLD/'candidate.json').read_text(encoding='utf-8'))
    c.update(stage_id='B2-SCOPE-09',version='b2_joint_preflight_candidate_v1',
        status='IMPLEMENTATION_CANDIDATE_NOT_AUTHORIZED',runner_implemented=True,
        cumulative_dynamic=225,parent=old['parent'],static_cases=[],design_sha256=sha(DESIGN/'admission_proposal.json'))
    c['proposed_limits']=dict(dynamic_attempts=12,static_attempts=0,environment_creations=12,resets=12,
        control_cycles_per_episode=14500,physical_substeps_per_episode=145000,control_cycles_total=174000,
        physical_substeps_total=1740000,per_episode_wall_s=1200,total_supervised_wall_s=21600,
        learner_constructions=0,tensor_reads=0,network_forwards=0,optimizer_updates=0,replay_publications=0)
    c['draft_scope_key']=hashlib.sha256(json.dumps(c,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    write(OUT/'candidate.json',c)
    for name in ('execution_contract.py','run_preflight.py','physical_worker.py','assess.py','offline_math.py',
                 'evidence_checks.py','windows_job.py','deadline_guard.py'):
        shutil.copyfile(OLD/name,OUT/name)
    write(OUT/'registration.json',dict(stage_id='B2-SCOPE-09',before_documents=before,
        design_manifest_sha256=sha(DESIGN/'delivery_manifest.json'),design_proposal_sha256=c['design_sha256'],
        inherited_sources={n:sha(OLD/n) for n in ('execution_contract.py','run_preflight.py','physical_worker.py',
            'assess.py','offline_math.py','evidence_checks.py','windows_job.py','deadline_guard.py')},
        proposal_sha256=sha(OUT/'candidate.json'),physical_authorized=False,training_admitted=False))
    print('Prepared candidate and immutable before snapshots; no physical execution.')

if __name__=='__main__':main()
