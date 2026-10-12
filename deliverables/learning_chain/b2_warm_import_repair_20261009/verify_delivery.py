"""Verify this offline candidate and previous immutable deliveries with stdlib only."""
import argparse,ast,json,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];sys.path.insert(0,str(HERE))
from joint_contract import read,write,sha,digest,canonical
from gate_contract import LIMITS,ROLE_LIMITS,WHOLE_WALL_S,READER_WALL_S,verify_sources
from gate_worker import NoPhysics
from import_graph import collect_graph,check_guard
PREV=HERE.parent/'b2_warm_reconstruction_preparation_20261009'
FAILED=HERE.parent/'b2_warm_reconstruction_execution_20261009'

def main():
    p=argparse.ArgumentParser();p.add_argument('--seal',action='store_true');p.add_argument('--current-docs',action='store_true');a=p.parse_args()
    if a.seal and (HERE/'delivery_manifest.json').exists():raise FileExistsError('Never reseal')
    checks=0
    def check(ok,label):
        nonlocal checks
        if not ok:raise AssertionError(label)
        checks+=1
    reg=read(HERE/'registration.json');docs=read(HERE/'document_update.json')
    check(sha(FAILED/'delivery_manifest.json')==reg['failure_seal'],'previous failure seal')
    check(sha(PREV/'delivery_manifest.json')==reg['previous_candidate_seal'],'previous candidate seal')
    proc=subprocess.run([sys.executable,'-I','-X','utf8','-B',str(FAILED/'verify_closed.py')],cwd=ROOT,capture_output=True,text=True,encoding='utf8',check=True)
    prior=json.loads(proc.stdout.strip().splitlines()[-1])
    check(prior['old_sealed_members_preserved']+prior['sealed_files']==3163,'all 3163 old sealed members preserved')
    for name,pin in reg['copies'].items():
        check(sha(PREV/name)==pin,'unchanged old source '+name)
        if name not in ('gate_worker.py','prepare_candidate.py'):check(sha(HERE/name)==pin,'unchanged copied module '+name)
    tree=ast.parse((HERE/'gate_worker.py').read_text(encoding='utf8'));old=ast.parse((PREV/'gate_worker.py').read_text(encoding='utf8'))
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='NoPhysics');method=cls.body[0]
    exception=method.body.pop(0)
    check(ast.dump(exception)==ast.dump(ast.parse("if fullname=='tools.dynamics.safety':return None").body[0]),'one exact pure helper exception')
    check(ast.dump(tree)==ast.dump(old),'worker unchanged beyond exact helper exception')
    binding=read(HERE/'source_binding.json');verify_sources(binding);checks+=len(binding['files'])+len(binding['inventories'])
    candidate=read(HERE/'candidate.json');request=read(HERE/'authorization_request.json')
    audit=read(HERE/'import_audit.json');graph=collect_graph(ROOT,HERE,['numeric_state','gate_worker','run_gate'])
    check(canonical(audit['graph'])==canonical(graph),'fresh import graph matches saved evidence')
    check_guard(graph,NoPhysics());checks+=1
    check(audit['old_guard_rejections']==['tools.dynamics.safety'] and audit['new_guard_rejections']==[],'targeted import defect')
    helper=audit['exact_exception'];check(helper['module']=='tools.dynamics.safety' and sha(helper['path'])==helper['sha256'],'reviewed helper identity')
    check(audit['runtime_import_verified'] is False and audit['numeric_restore_verified'] is False,'static scope only')
    check(candidate['stage_id']=='B2-SCOPE-17' and candidate['import_audit_sha256']==sha(HERE/'import_audit.json'),'new candidate binds import audit')
    check(candidate['supersedes_failed_candidate']==digest(read(PREV/'candidate.json')),'separate replacement candidate')
    check(candidate['status']=='PREPARED_NOT_AUTHORIZED' and not candidate['numeric_verified'] and not candidate['training_admitted'],'preparation only')
    check(candidate['limits']==request['limits']==LIMITS and candidate['role_limits']==ROLE_LIMITS,'operation scopes')
    check(candidate['whole_wall_s']==request['whole_wall_s']==WHOLE_WALL_S and candidate['reader_wall_s']==request['reader_wall_s']==READER_WALL_S,'wall bounds')
    check(candidate['source_binding_sha256']==request['binding_sha256']==sha(HERE/'source_binding.json'),'source binding')
    check(candidate['input_spec_sha256']==digest(read(HERE/'input_spec.json')),'input specification')
    check(request['candidate_sha256']==digest(candidate) and request['status']=='NOT_AUTHORIZED' and request['explicit_user_authorized'] is False,'unsigned request')
    for name,pin in candidate['code_sha256'].items():check(sha(HERE/name)==pin,'candidate code '+name)
    # Once sealed, this describes the historical preparation; later standalone runs may consume its claim.
    if not (HERE/'delivery_manifest.json').exists():
        check(not (HERE/'future_claims').exists() and not (HERE/'grant.json').exists() and not (HERE/'checkpoint').exists(),'no numeric execution at preparation')
    test=read(HERE/docs['test_report'])
    check(test['successful'] and test['failures']==test['errors']==test['skipped']==0,'all offline tests pass')
    check(not test['forbidden_imports'] and all(test[k]==0 for k in ('physics','learner_constructions','checkpoint_loads','network_forwards','updates','replay_publications')),'no scientific operations')
    review=read(HERE/'review_resolution.json');check(review['status']=='RESOLVED' and review['open_critical']==review['open_important']==0,'review resolved')
    for name,pin in reg['before_documents'].items():
        check(sha(HERE/'before_documents'/name)==pin,'before snapshot '+name)
        check(sha(HERE/'document_snapshots'/name)==docs['after_documents'][name],'after snapshot '+name)
        if a.current_docs:check(sha(ROOT/name)==docs['after_documents'][name],'current '+name)
    git=lambda *args:subprocess.check_output(['git',*args],cwd=ROOT).decode('utf8')
    check(git('branch','--show-current').strip()==reg['branch'] and git('rev-parse','HEAD').strip()==reg['head'],'branch and HEAD unchanged')
    before=set((HERE/'git_status_before.txt').read_text(encoding='utf8').splitlines());after=set(git('status','--porcelain=v1').splitlines())
    check(not before-after,'all earlier dirty entries preserved')
    for path in HERE.glob('*.py'):ast.parse(path.read_text(encoding='utf8'));checks+=1
    for path in (HERE/'test_work').glob('*/*.supervisor.json'):
        receipt=read(path);check(receipt['process_exit_confirmed'] and receipt['owned_launcher_exit_confirmed'],'owned test process exited')
    check(not any(k.split('.')[0] in ('numpy','torch','mujoco','stable_baselines3') for k in sys.modules),'stdlib verification')
    result=dict(stage_id='B2-SCOPE-17',status='VERIFIED_OFFLINE_IMPORT_REPAIR_ONLY',checks=checks,tests=test['tests'],
        old_sealed_members_preserved=3163,prior_bound_inputs_preserved=prior['bound_inputs_preserved'],bound_inputs=len(binding['files']),
        graph_modules=len(graph['modules']),eager_import_records=len(graph['eager_edges']),deferred_import_records=len(graph['deferred_edges']),runtime_import_verified=False,
        numeric_restore_verified=False,training_admitted=False,physics=0,checkpoint_loads=0,formal_updates=0,
        cumulative_dynamic=245,automatic_tracking='PAUSED',full_B2_accepted=False,C_accepted=False,independent_tests=0)
    if a.seal:
        write(HERE/'prior_verification.json',prior);write(HERE/'verification.json',result)
        (HERE/'git_status_after.txt').write_text(git('status','--porcelain=v1'),encoding='utf8')
        files={p.relative_to(HERE).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(HERE.rglob('*'))
            if p.is_file() and p.name!='delivery_manifest.json' and '__pycache__' not in p.parts}
        write(HERE/'delivery_manifest.json',dict(stage_id='B2-SCOPE-17',files=files,rolling_documents_may_advance=True))
    if (HERE/'delivery_manifest.json').exists():
        members=read(HERE/'delivery_manifest.json')['files']
        for name,v in members.items():check(sha(HERE/name)==v['sha256'] and (HERE/name).stat().st_size==v['bytes'],'sealed '+name)
        result.update(checks=checks,sealed_files=len(members),manifest_sha256=sha(HERE/'delivery_manifest.json'))
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
