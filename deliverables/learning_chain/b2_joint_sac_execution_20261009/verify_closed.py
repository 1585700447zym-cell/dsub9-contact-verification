"""Verify the closed execution without importing native or learning runtimes."""
import argparse
import ast
import json
from pathlib import Path
import subprocess
import sys
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];KIT=OUT.parent/'b2_joint_sac_preparation_20261009'
sys.path.insert(0,str(KIT))
from joint_contract import read,write,sha,digest
from execution import verify_sources


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--seal',action='store_true');parser.add_argument('--current-docs',action='store_true');args=parser.parse_args()
    if args.seal and (OUT/'delivery_manifest.json').exists():raise PermissionError('Do not rewrite a seal')
    checks=0
    def check(ok,label):
        nonlocal checks
        if not ok:raise AssertionError(label)
        checks+=1
    reg=read(OUT/'registration.json');s=read(OUT/'execution_summary.json');folder=OUT/'execution'
    check(reg['user_message']=='批准继续' and reg['grant_validated'],'explicit human approval')
    check(digest(read(OUT/'grant.json'))==reg['grant_sha256'],'grant identity')
    check(read(folder/'grant.json')==read(OUT/'grant.json'),'run uses same grant')
    claim=read(KIT/'future_claims/consumed.json')
    check(claim['grant_sha256']==reg['grant_sha256'] and claim['output']==str(folder),'one consumed claim')
    for name,pin in reg['runner_pins'].items():check(sha(KIT/name)==pin,'unchanged runner '+name)
    for name,item in read(KIT/'delivery_manifest.json')['files'].items():check(sha(KIT/name)==item['sha256'] and (KIT/name).stat().st_size==item['bytes'],'candidate member '+name)
    binding=read(KIT/'source_binding.json');verify_sources(binding);check(len(binding['files'])==2555,'all bound inputs intact')
    prior=OUT.parent/'b2_joint_coverage_review_20261009/verify_delivery.py'
    proc=subprocess.run([sys.executable,'-I','-X','utf8','-B',str(prior)],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',check=True)
    old=json.loads(proc.stdout.strip().splitlines()[-1]);check(old['preserved_sealed_members']+old['sealed_files']+47==1869,'all old1869 sealed members')
    closure=read(folder/'authorization_closure.json');counter=read(folder/'counter.json');supervisor=read(folder/'supervisor.supervisor.json')
    check(counter['status']=='CLOSED' and closure['unused_closed'] and closure['no_retry'],'all remaining quota closed')
    check(supervisor['process_exit_confirmed'] and supervisor['owned_launcher_exit_confirmed'] and closure['process_exit_confirmed'],'owned tree exit')
    check(s['status']==closure['status'] and not s['training_admitted'],'closed summary not training permit')
    for key,limit in counter['limits'].items():check(0<=counter['attempted'][key]<=limit and counter['unused_closed'][key]==limit-counter['attempted'][key],'bounded '+key)
    check(s['cumulative_dynamic']==237+s['attempts'] and s['attempts']<=17 and s['updates_completed']<=2000,'actual count within grant')
    ledger=read(folder/'run/ledger.json')
    check(len(ledger['episodes'])==len(s['episodes'])==9 and counter['attempted']['environment_creations']==s['attempts']==8,'nine registered rows but eight physical episodes')
    check(sum(r['physical_reserved'] for r in s['episodes'])==8 and s['episodes'][-1]['execution_class']=='REGISTERED_NOT_STARTED_CLOSED','last registration not a physical attempt')
    check(s['updates_completed']==s['update_attempts']==0 and not (folder/'run/chain/update_journal.jsonl').exists(),'no update transaction')
    check(all(r['outcome']['task_outcome']=='FULL_SUCCESS' and r['healthy'] for r in s['episodes'][:8]),'eight complete task successes')
    check([c['label'] for c in s['checkpoints']]==['zero'] and not (folder/'run/checkpoints/final').exists(),'only zero checkpoint saved')
    diagnosis=read(OUT/'failure_diagnosis.json');probe=read(OUT/'phase_io_probe.json')
    for name,pin in diagnosis['source_pins'].items():check(sha(OUT/name)==pin,'diagnosis evidence '+name)
    for name,pin in diagnosis['candidate_source_pins'].items():check(sha(KIT/name)==pin,'unmodified failure source '+name)
    check('PermissionError' in supervisor['error'] and not supervisor['deadline_hit'],'supervisor read error not timeout')
    check('phase=read(phase_file)' in (OUT/'launcher.log').read_text(encoding='utf-8'),'original traceback read site')
    check(read(folder/'phase_deadline.json')['id']=='online_F50_J01','failed online boundary')
    check(probe['new_physics']==probe['new_learning']==0 and probe['wall_s']<15,'bounded file-only probe')
    for side in ('read','write'):
        check(probe[side+'_permission_errors']==sum(e['side']==side and e['type']=='PermissionError' for e in probe['errors'])>0,'reproduced '+side+' error')
    check(not diagnosis['implementation_fixed'] and not diagnosis['restart_authorized'],'diagnosis does not claim fix or restart')
    for row in s['episodes']:
        if 'archive_sha256' in row:check(sha(folder/'run'/(row['id']+'.json.gz'))==row['archive_sha256'],'physical archive '+row['id'])
    for checkpoint in s['checkpoints']:
        p=folder/'run/checkpoints'/checkpoint['label'];check(sha(p/'manifest.json')==checkpoint['manifest_sha256'] and sha(p/'state.pt')==checkpoint['state_sha256'],'opaque checkpoint bytes')
    docs=read(OUT/'document_update.json')
    for name,pin in reg['before_documents'].items():
        check(sha(OUT/'before_documents'/name)==pin,'before document')
        check(sha(OUT/'document_snapshots'/name)==docs['after_documents'][name],'after document snapshot')
        if args.current_docs:check(sha(ROOT/name)==docs['after_documents'][name],'current document snapshot')
        if name!='AGENTS.md':
            body=(OUT/'document_snapshots'/name).read_text(encoding='utf-8').split('<!-- b2-scope-current -->',1)[1].split('<!-- /b2-scope-current -->',1)[0]
            check('CLOSED_ERROR' in body and '累计动态245' in body and 'PermissionError' in body and '正在执行' not in body,'current closed documentation '+name)
    git=lambda *a:subprocess.check_output(['git',*a],cwd=ROOT).decode('utf-8')
    check(git('branch','--show-current').strip()==reg['branch'] and git('rev-parse','HEAD').strip()==reg['head'],'same worktree branch and HEAD')
    before=set((OUT/'git_status_before.txt').read_text(encoding='utf-8').splitlines());after=set(git('status','--porcelain=v1').splitlines())
    check(not before-after,'prior dirty entries preserved')
    for p in OUT.glob('*.py'):ast.parse(p.read_text(encoding='utf-8'));checks+=1
    check(not any(k.split('.')[0] in {'numpy','torch','mujoco','stable_baselines3'} for k in sys.modules),'no backend in closeout')
    result=dict(stage_id='B2-SCOPE-13',status='VERIFIED_CLOSED_EXECUTION',checks=checks,
        run_status=s['status'],old_sealed_members_preserved=1869,bound_inputs=2555,
        dynamic_attempts=s['attempts'],complete_raw_archives=s['complete_raw_archives'],formal_updates_completed=s['updates_completed'],
        cumulative_dynamic=s['cumulative_dynamic'],failure_class=diagnosis['failure_class'],
        implementation_fixed=False,full_B2_accepted=False,C_accepted=False,automatic_tracking='PAUSED',training_admitted=False)
    if args.seal:
        write(OUT/'prior_verification.json',old);write(OUT/'verification.json',result)
        (OUT/'git_status_after.txt').write_text(git('status','--porcelain=v1'),encoding='utf-8')
        files={p.relative_to(OUT).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='delivery_manifest.json' and '__pycache__' not in p.parts}
        write(OUT/'delivery_manifest.json',dict(stage_id='B2-SCOPE-13',files=files,rolling_documents_may_advance=True))
    if (OUT/'delivery_manifest.json').exists():
        members=read(OUT/'delivery_manifest.json')['files']
        for name,item in members.items():check(sha(OUT/name)==item['sha256'] and (OUT/name).stat().st_size==item['bytes'],'sealed '+name)
        result.update(checks=checks,sealed_files=len(members),manifest_sha256=sha(OUT/'delivery_manifest.json'))
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
