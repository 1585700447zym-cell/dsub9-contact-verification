"""Read-only stdlib audit of the failed one-shot gate, prior seals and project snapshots."""
import argparse,ast,json,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
KIT=HERE.parent/'b2_warm_reconstruction_preparation_20261009';sys.path.insert(0,str(KIT))
from joint_contract import read,write,sha,digest
from gate_contract import verify_grant,LIMITS,Gate

def main():
    p=argparse.ArgumentParser();p.add_argument('--seal',action='store_true');p.add_argument('--current-docs',action='store_true');a=p.parse_args()
    if a.seal and (HERE/'delivery_manifest.json').exists():raise FileExistsError('Never reseal')
    checks=0
    def check(ok,label):
        nonlocal checks
        if not ok:raise AssertionError(label)
        checks+=1
    reg=read(HERE/'launch_registration/registration.json')
    check(sha(KIT/'delivery_manifest.json')==reg['preparation_manifest_sha256'],'approved preparation seal')
    proc=subprocess.run([sys.executable,'-I','-X','utf8','-B',str(KIT/'verify_delivery.py')],cwd=ROOT,capture_output=True,text=True,encoding='utf8',check=True)
    prior=json.loads(proc.stdout.strip().splitlines()[-1])
    check(prior['old_sealed_members_preserved']+prior['sealed_files']==3123,'3123 prior sealed members preserved')
    check(prior['bound_inputs']==2582,'all prepared source bindings preserved')
    grant=read(HERE/'grant.json');pin=read(HERE/'grant_pin.json')['sha256'];candidate=read(KIT/'candidate.json')
    check(digest(grant)==pin==reg['grant_sha256']==digest(read(HERE/'launch_registration/grant.json')),'single approved grant')
    verify_grant(candidate,grant,pin,sha(KIT/'source_binding.json'));checks+=1
    check(read(KIT/'future_claims/consumed.json')==dict(grant_sha256=pin,output=str(HERE.resolve())),'one-shot claim belongs to this run')
    counter=read(HERE/'counter.json');closure=read(HERE/'authorization_closure.json');supervisor=read(HERE/'supervisor.supervisor.json')
    check(counter['status']=='CLOSED' and closure['status']=='CLOSED_ERROR','error closed, never qualified')
    check(counter['limits']==reg['limits']==LIMITS and counter['unused_closed']==LIMITS,'all unused operations expired')
    check(set(counter['attempted'])==set(LIMITS) and all(type(v) is int and v==0 for v in counter['attempted'].values()),'no counted operations attempted')
    check(counter['roles']['parent']['claimed'] is True and counter['roles']['reader']['claimed'] is False,'parent admitted, reader never claimed')
    for role in ('parent','reader'):check(all(v==0 for v in counter['roles'][role]['attempted'].values()),'role operations zero '+role)
    check(closure['counter_closed'] and closure['unused_closed'] and closure['no_retry'],'durable closure')
    check(closure['counter_error'] is None and closure['receipt_error'] is None,'no failure during closure')
    check(closure['process_exit_confirmed'] and supervisor['process_exit_confirmed'] and supervisor['owned_launcher_exit_confirmed'],'owned tree exited')
    check(supervisor['go_issued'] and supervisor['returncode']==1 and not supervisor['deadline_hit'],'actual import failure, no timeout')
    check(0<supervisor['wall_seconds']<grant['whole_wall_s'],'elapsed within cap')
    check(closure['automatic_tracking']=='PAUSED' and closure['cumulative_dynamic']==245 and closure['training_admitted'] is False,'research scope unchanged')
    try:Gate(HERE,'parent')
    except PermissionError as exc:check('closed authorization' in str(exc),'closed grant refused before any numeric import')
    else:raise AssertionError('Closed grant remained usable')
    for name in ('checkpoint','reader_request.json','reader_reply.json','reader.ready.json','reader.go.json','reader.supervisor.json','assessment.json'):
        check(not (HERE/name).exists(),'no unearned artifact '+name)
    diagnosis=read(HERE/'failure_diagnosis.json')
    check(diagnosis['status']=='CONFIRMED_IMPORT_GUARD_FALSE_POSITIVE' and not diagnosis['numeric_restore_verified'],'failure diagnosis only')
    check(diagnosis['actual_operations']==counter['attempted'] and not diagnosis['diagnostic_forbidden_imports'],'pure diagnostic activity')
    for path,pin in diagnosis['source_pins'].items():check(sha(path)==pin,'diagnostic source '+path)
    log=(HERE/'supervisor.log').read_text(encoding='utf8')
    check('from tools.dynamics.safety import limit_command' in log and 'PermissionError: Physical backend forbidden in restore gate' in log,'trace confirms blocked helper')
    launch=read(HERE/'launch_registration/launcher_result.json');check(launch['returncode']==1 and launch['no_retry'],'outer launcher failed once')
    bootstrap=read(HERE/'launch_registration/bootstrap_path_error.json')
    check(bootstrap['numeric_operations']==0 and all(bootstrap[k] is False for k in ('registration_created','grant_created','candidate_claim_created','numeric_output_created')),'separate pre-admission path error preserved')
    review=read(HERE/'review_resolution.json');check(review['status']=='RESOLVED' and review['open_critical']==review['open_important']==0,'failure evidence review complete')
    docs=read(HERE/'document_update.json')
    for name,pin in reg['before_documents'].items():
        check(sha(HERE/'launch_registration/before_documents'/name)==pin,'before snapshot '+name)
        check(sha(HERE/'document_snapshots'/name)==docs['after_documents'][name],'after snapshot '+name)
        if a.current_docs:check(sha(ROOT/name)==docs['after_documents'][name],'current document '+name)
    git=lambda *x:subprocess.check_output(['git',*x],cwd=ROOT).decode('utf8')
    check(git('branch','--show-current').strip()==reg['branch'] and git('rev-parse','HEAD').strip()==reg['head'],'branch and HEAD unchanged')
    before=set((HERE/'launch_registration/git_status_before.txt').read_text(encoding='utf8').splitlines());after=set(git('status','--porcelain=v1').splitlines())
    check(not before-after,'previous dirty entries preserved')
    for f in HERE.glob('*.py'):ast.parse(f.read_text(encoding='utf8'));checks+=1
    check(not any(k.split('.')[0] in ('numpy','torch','mujoco','stable_baselines3') for k in sys.modules),'no numeric runtime during closure audit')
    result=dict(stage_id='B2-SCOPE-16',status='VERIFIED_FAILURE_CLOSEOUT',checks=checks,
        execution_status='CLOSED_ERROR',reason=diagnosis['status'],actual_operations=counter['attempted'],
        numeric_restore_verified=False,training_admitted=False,reader_started=False,checkpoint_created=False,
        runtime_import_started=True,process_exit_confirmed=True,old_sealed_members_preserved=3123,bound_inputs_preserved=2582,
        prior_offline_tests=61,new_numerical_success=False,cumulative_dynamic=245,automatic_tracking='PAUSED',
        full_B2_accepted=False,C_accepted=False,independent_tests=0,supervisor_wall_s=supervisor['wall_seconds'],no_retry=True)
    if a.seal:
        write(HERE/'prior_verification.json',prior);write(HERE/'verification.json',result)
        (HERE/'git_status_after.txt').write_text(git('status','--porcelain=v1'),encoding='utf8')
        files={p.relative_to(HERE).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(HERE.rglob('*'))
            if p.is_file() and p.name!='delivery_manifest.json' and '__pycache__' not in p.parts}
        write(HERE/'delivery_manifest.json',dict(stage_id='B2-SCOPE-16',files=files,rolling_documents_may_advance=True))
    if (HERE/'delivery_manifest.json').exists():
        members=read(HERE/'delivery_manifest.json')['files']
        for name,record in members.items():check(sha(HERE/name)==record['sha256'] and (HERE/name).stat().st_size==record['bytes'],'sealed '+name)
        result.update(checks=checks,sealed_files=len(members),manifest_sha256=sha(HERE/'delivery_manifest.json'))
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
