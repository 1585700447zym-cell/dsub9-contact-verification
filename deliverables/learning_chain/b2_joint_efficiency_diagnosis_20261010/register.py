"""Register a read-only archive study; never issue a new scientific grant."""
import hashlib,json,shutil,subprocess,sys
from pathlib import Path
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
PRIOR=OUT.parent/'b2_joint_sac_continuation_execution_20261009'
PRIOR_SEAL='3fc16b55a67430b889caa1598ce96eb47f7dca92f7ac7f93358f3598c17e65b4'
PLAN='docs/superpowers/plans/2026-10-10-b2-joint-efficiency-diagnosis.md'
DOCS=('AGENTS.md','项目当前入口.md','项目进度跟踪.md','研究推进计划_当前版.md','项目交付总览.md','deliverables/monthly_progress/2026-10/月报素材_2026-10.md')
SOURCE=('tools/learning/reward.py','tools/learning/observation.py','tools/learning/v4_observation.py','tools/learning/v4_action.py',
        'tools/learning/action.py','tools/learning/v4_continuation.py','tools/learning/v4_session.py','tools/learning/session.py',
        'tools/model/layered_task.py','tools/validation/run_v4_adapter_preflight.py','tools/control/reference_search.py','tools/control/compliant_search.py')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def write(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n',encoding='utf8')
if __name__=='__main__':
    if (OUT/'registration.json').exists():raise FileExistsError('Preserve first registration')
    if sha(PRIOR/'delivery_manifest.json')!=PRIOR_SEAL:raise ValueError('Wrong SCOPE20 seal')
    check=subprocess.run([sys.executable,'-I','-X','utf8','-B',str(PRIOR/'verify_closed.py'),'--current-docs'],cwd=ROOT,capture_output=True,text=True,encoding='utf8')
    (OUT/'prior_verification.log').write_text(check.stdout+check.stderr,encoding='utf8')
    if check.returncode:raise RuntimeError('Prior closeout check failed; no analysis started')
    proof=json.loads(check.stdout.strip().splitlines()[-1]);write(OUT/'prior_verification.json',proof)
    if proof['execution_status']!='CLOSED_COMPLETE' or proof['sealed_files']!=139 or proof['old_sealed_members_preserved']!=3546:raise ValueError('Wrong historical closeout')
    ledger=read(PRIOR/'run/ledger.json');archives=[];members=read(PRIOR/'delivery_manifest.json')['files']
    for i in range(4):
        b=ledger['inherited_sources']['baseline'][i];archives.append(dict(model='F0',case_id='J0'+str(i+1),path=str(Path(b['archive']).resolve()),sha256=b['archive_sha256']))
        name='run/final_F50_J0'+str(i+1)+'.json.gz';archives.append(dict(model='F2000',case_id='J0'+str(i+1),path=str((PRIOR/name).resolve()),sha256=members[name]['sha256']))
    for item in archives:
        if sha(item['path'])!=item['sha256']:raise ValueError('Archive changed '+item['case_id'])
    before={}
    for name in DOCS:
        dst=OUT/'before_documents'/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dst);before[name]=sha(dst)
    git=lambda *x:subprocess.check_output(['git',*x],cwd=ROOT).decode('utf8')
    status=git('status','--porcelain=v1');(OUT/'git_status_before.txt').write_text(status,encoding='utf8')
    branch=git('branch','--show-current').strip();head=git('rev-parse','HEAD').strip()
    if branch!='feature/dsub9-dynamic-actuator-v1' or head!='d2e7e4fa4ed0631d9dd1b7b98a121c1e46ea6406':raise ValueError('Branch or HEAD changed')
    shutil.copyfile(ROOT/PLAN,OUT/'plan_snapshot.md')
    write(OUT/'registration.json',dict(stage_id='B2-SCOPE-21',date='2026-10-10',task='Existing F0/F2000 archive efficiency and precision diagnosis',
         branch=branch,head=head,before_documents=before,archives=archives,source_code_sha256={n:sha(ROOT/n) for n in SOURCE},
         prior_directory=str(PRIOR),prior_manifest_sha256=PRIOR_SEAL,old_sealed_members=3685,plan=PLAN,plan_sha256=sha(ROOT/PLAN),
         costs=dict(new_dynamic_episodes=0,new_physical_substeps=0,new_policy_inferences=0,new_tensor_loads=0,new_model_constructions=0,new_optimizer_updates=0,new_published_transitions=0),
         cumulative_dynamic=254,automatic_tracking='PAUSED',training_admitted=False,independent_tests=0,full_B2_accepted=False,C_accepted=False))
    print('Registered 8 existing archives; 3685 historical members preserved; scientific execution 0.')
