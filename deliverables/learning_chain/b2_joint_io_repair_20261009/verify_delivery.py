"""Verify offline repair evidence and prior seals without scientific runtimes."""
import argparse
import ast
import json
from pathlib import Path
import subprocess
import sys
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];sys.path.insert(0,str(HERE))
from joint_contract import read,write,sha
OLD=HERE.parent/'b2_joint_sac_execution_20261009';KIT=HERE.parent/'b2_joint_sac_preparation_20261009'

def main():
    p=argparse.ArgumentParser();p.add_argument('--seal',action='store_true');p.add_argument('--current-docs',action='store_true');args=p.parse_args()
    if args.seal and (HERE/'delivery_manifest.json').exists():raise FileExistsError('Do not reseal')
    checks=0
    def check(ok,label):
        nonlocal checks
        if not ok:raise AssertionError(label)
        checks+=1
    reg=read(HERE/'registration.json');docs=read(HERE/'document_update.json')
    check(sha(OLD/'delivery_manifest.json')==reg['old_manifest_sha256'],'prior seal identity')
    proc=subprocess.run([sys.executable,'-I','-X','utf8','-B',str(OLD/'verify_closed.py')],cwd=ROOT,capture_output=True,text=True,encoding='utf8',check=True)
    prior=json.loads(proc.stdout.strip().splitlines()[-1]);check(prior['old_sealed_members_preserved']+prior['sealed_files']==2617,'all 2617 old sealed members')
    for name,pin in reg['base_sources'].items():check(sha(KIT/name)==pin,'old source '+name)
    check(sha(HERE/'windows_job.py')==sha(KIT/'windows_job.py'),'same Job implementation')
    check(sha(HERE/'test_related_contract.py')==sha(KIT/'test_joint_contract.py'),'unchanged related contract tests')
    def contract_body(path):
        tree=ast.parse(path.read_text(encoding='utf8'))
        tree.body=[n for n in tree.body if not (isinstance(n,ast.FunctionDef) and n.name in ('read','write')) and not (isinstance(n,ast.ImportFrom) and n.module=='bounded_io')]
        return ast.dump(tree)
    check(contract_body(HERE/'joint_contract.py')==contract_body(KIT/'joint_contract.py'),'research contract unchanged beyond I/O')
    test=read(HERE/docs['test_report']);check(test['successful'] and test['failures']==test['errors']==test['skipped']==0,'complete offline suite')
    check(not test['forbidden_imports'] and all(test[k]==0 for k in ('physics','learner_constructions','checkpoint_loads','network_forwards','updates','replay_publications')),'no scientific runtime test activity')
    r=read(HERE/'recovery_assessment.json')
    for name,pin in r['source_pins'].items():check(sha(ROOT/name)==pin,'recovery input '+name)
    check(r['replay_rows']==19300 and r['warm_vector_draws']==388 and r['active_rows']==14127,'archived warmup facts')
    check(not r['numeric_restore_verified'] and not r['lossless_resume_verified'] and not r['restart_authorized'],'source audit not numeric qualification')
    review=read(HERE/'review_resolution.json');check(review['status']=='RESOLVED' and review['open_critical']==review['open_important']==0,'review closure')
    for name,pin in reg['before_documents'].items():
        check(sha(HERE/'before_documents'/name)==pin,'before document '+name)
        check(sha(HERE/'document_snapshots'/name)==docs['after_documents'][name],'snapshot '+name)
        if args.current_docs:check(sha(ROOT/name)==docs['after_documents'][name],'current document '+name)
    git=lambda *a:subprocess.check_output(['git',*a],cwd=ROOT).decode('utf8')
    check(git('branch','--show-current').strip()==reg['branch'] and git('rev-parse','HEAD').strip()==reg['head'],'branch and HEAD preserved')
    before=set((HERE/'git_status_before.txt').read_text(encoding='utf8').splitlines());after=set(git('status','--porcelain=v1').splitlines())
    check(not before-after,'all previous dirty entries retained')
    for path in HERE.glob('*.py'):ast.parse(path.read_text(encoding='utf8'));checks+=1
    check(not any(k.split('.')[0] in ('numpy','torch','mujoco','stable_baselines3') for k in sys.modules),'stdlib-only verification')
    for path in (HERE/'test_work').glob('*/control.supervisor.json'):
        receipt=read(path);check(receipt['process_exit_confirmed'] and receipt['owned_launcher_exit_confirmed'],'test-owned process exit')
    result=dict(stage_id='B2-SCOPE-14',status='VERIFIED_OFFLINE_REPAIR_AND_RECOVERY_SOURCES',checks=checks,
        tests=test['tests'],old_sealed_members_preserved=2617,bound_inputs_preserved=prior['bound_inputs'],
        replay_source_rows=19300,active_source_rows=14127,physics=0,checkpoint_loads=0,formal_updates=0,
        numeric_restore_verified=False,restart_authorized=False,cumulative_dynamic=245,automatic_tracking='PAUSED',full_B2_accepted=False,C_accepted=False)
    if args.seal:
        write(HERE/'prior_verification.json',prior);write(HERE/'verification.json',result)
        (HERE/'git_status_after.txt').write_text(git('status','--porcelain=v1'),encoding='utf8')
        plan=ROOT/'docs/superpowers/plans/2026-10-09-b2-joint-io-repair.md'
        (HERE/'implementation_plan.md').write_bytes(plan.read_bytes())
        files={p.relative_to(HERE).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(HERE.rglob('*')) if p.is_file() and p.name!='delivery_manifest.json' and '__pycache__' not in p.parts}
        write(HERE/'delivery_manifest.json',dict(stage_id='B2-SCOPE-14',files=files,rolling_documents_may_advance=True))
    if (HERE/'delivery_manifest.json').exists():
        members=read(HERE/'delivery_manifest.json')['files']
        for name,v in members.items():check(sha(HERE/name)==v['sha256'] and (HERE/name).stat().st_size==v['bytes'],'sealed '+name)
        result.update(checks=checks,sealed_files=len(members),manifest_sha256=sha(HERE/'delivery_manifest.json'))
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
