"""Stdlib-only candidate audit and immutable evidence seal."""
import argparse, ast, json, subprocess, sys
from pathlib import Path
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];sys.path.insert(0,str(OUT))
from joint_contract import read,write,sha,digest,LIMITS,learning_config,schedule,canonical
from execution import verify_sources,verify_code
PREV=OUT.parent/'b2_warm_restore_execution_20261009'

def main():
    p=argparse.ArgumentParser();p.add_argument('--seal',action='store_true');p.add_argument('--current-docs',action='store_true');p.add_argument('--preflight',action='store_true');a=p.parse_args()
    if a.seal and (a.preflight or (OUT/'delivery_manifest.json').exists()):raise FileExistsError('Never reseal or seal an incomplete audit')
    checks=0
    def check(ok,label):
        nonlocal checks
        if not ok:raise AssertionError(label)
        checks+=1
    reg=read(OUT/'registration.json')
    check(sha(PREV/'delivery_manifest.json')==reg['previous_restore_seal'],'unchanged approved restoration seal')
    proc=subprocess.run([sys.executable,'-I','-X','utf8','-B',str(PREV/'verify_closed.py')],cwd=ROOT,capture_output=True,text=True,encoding='utf8',check=True)
    prior=json.loads(proc.stdout.strip().splitlines()[-1])
    check(prior['old_sealed_members_preserved']+prior['sealed_files']==3491,'3491 prior sealed members')
    check(prior['numeric_restore_verified'] and not prior['training_admitted'],'previous component restore only')
    binding=read(OUT/'source_binding.json');verify_sources(binding);checks+=len(binding['files'])+len(binding['inventories'])
    candidate=read(OUT/'candidate.json');request=read(OUT/'authorization_request.json');spec=read(OUT/'input_spec.json')
    check(candidate['version']=='b2_joint_continuation_candidate_v1' and candidate['stage_id']=='B2-SCOPE-19','new continuation identity')
    check(candidate['status']=='PREPARED_NOT_AUTHORIZED' and candidate['training_admitted'] is False and candidate['numeric_continuation_verified'] is False,'offline preparation only')
    check(candidate['limits']==request['limits']==LIMITS and candidate['schedule']==schedule(),'exact remaining scope')
    check(candidate['cumulative_before']==245 and candidate['cumulative_ceiling']==254,'new dynamic ceiling only proposed')
    check(candidate['learning_config_sha256']==digest(learning_config())==spec['legacy_config_sha256'],'same learning configuration')
    check(request['candidate_sha256']==digest(candidate) and request['binding_sha256']==candidate['source_binding_sha256']==sha(OUT/'source_binding.json'),'request and source identity')
    check(request['status']=='NOT_AUTHORIZED' and request['explicit_user_authorized'] is False and not request['retry_allowed'] and not request['carryover_allowed'],'unsigned once-only request')
    verify_code(candidate);checks+=len(candidate['code_sha256'])
    check(candidate['input_spec_sha256']==digest(spec) and candidate['import_audit_sha256']==sha(OUT/'import_audit.json'),'candidate input and import pins')
    check(candidate['inherited_baseline_sha256']==sha(OUT/'inheritance_audit.json'),'frozen baseline inheritance audit')
    sys.path.insert(1,str(OUT.parent/'b2_warm_import_repair_20261009'))
    from import_graph import collect_graph
    audit=read(OUT/'import_audit.json');graph=collect_graph(ROOT,OUT,audit['roots'])
    check(canonical(graph)==canonical(audit['graph']),'fresh source import inventory')
    for record in graph['modules'].values():check(binding['files'].get(record['path'])==record['sha256'],'imported module pinned '+record['path'])
    check(audit['runtime_import_verified'] is False and audit['scientific_operations']==0,'actual runtime not executed')
    provenance=read(OUT/'adapter_provenance.json')
    for name,record in provenance.items():
        check(sha(record['source'])==record['before'],'unchanged source '+name)
        check(sha(OUT/name)==record['final_sha256'],'new adapter '+name)
    test=read(OUT/'suite_final.json')
    check(test['successful'] and test['failures']==test['errors']==test['skipped']==0,'all stdlib tests pass')
    check(not test['forbidden_imports'] and all(test[k]==0 for k in ('physics','learner_constructions','checkpoint_loads','network_forwards','formal_updates','new_experience')),'no numeric work in tests')
    check(not (OUT/'future_claims').exists() and not (OUT/'grant.json').exists() and not (OUT/'checkpoint').exists(),'candidate not executed')
    for name,pin in reg['before_documents'].items():check(sha(OUT/'before_documents'/name)==pin,'before snapshot '+name)
    if not a.preflight:
        review=read(OUT/'review_resolution.json');check(review['status']=='RESOLVED' and review['open_critical']==review['open_important']==0,'independent review complete')
        docs=read(OUT/'document_update.json')
        for name in reg['before_documents']:
            check(sha(OUT/'document_snapshots'/name)==docs['after_documents'][name],'after snapshot '+name)
            if a.current_docs:check(sha(ROOT/name)==docs['after_documents'][name],'current document '+name)
    git=lambda *x:subprocess.check_output(['git',*x],cwd=ROOT).decode('utf8')
    check(git('branch','--show-current').strip()==reg['branch'] and git('rev-parse','HEAD').strip()==reg['head'],'branch and HEAD preserved')
    before=set((OUT/'git_status_before.txt').read_text(encoding='utf8').splitlines());after=set(git('status','--porcelain=v1').splitlines())
    check(not before-after,'previous dirty entries preserved')
    for path in OUT.glob('*.py'):ast.parse(path.read_text(encoding='utf8'));checks+=1
    check(not any(k.split('.')[0] in ('numpy','torch','mujoco','stable_baselines3','gymnasium') for k in sys.modules),'stdlib-only delivery audit')
    result=dict(stage_id='B2-SCOPE-19',status='VERIFIED_OFFLINE_CONTINUATION_ONLY',checks=checks,tests=test['tests'],
                old_sealed_members_preserved=3491,bound_inputs=len(binding['files']),graph_modules=len(graph['modules']),
                eager_import_records=len(graph['eager_edges']),deferred_import_records=len(graph['deferred_edges']),
                numeric_continuation_verified=False,training_admitted=False,new_physics=0,new_updates=0,new_experience=0,
                cumulative_dynamic=245,automatic_tracking='PAUSED',full_B2_accepted=False,C_accepted=False,independent_tests=0)
    if a.seal:
        write(OUT/'prior_verification.json',prior);write(OUT/'verification.json',result)
        (OUT/'git_status_after.txt').write_text(git('status','--porcelain=v1'),encoding='utf8')
        files={p.relative_to(OUT).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(OUT.rglob('*'))
               if p.is_file() and p.name!='delivery_manifest.json' and '__pycache__' not in p.parts}
        write(OUT/'delivery_manifest.json',dict(stage_id='B2-SCOPE-19',files=files,rolling_documents_may_advance=True))
    if (OUT/'delivery_manifest.json').exists():
        members=read(OUT/'delivery_manifest.json')['files']
        for name,record in members.items():check(sha(OUT/name)==record['sha256'] and (OUT/name).stat().st_size==record['bytes'],'sealed '+name)
        result.update(checks=checks,sealed_files=len(members),manifest_sha256=sha(OUT/'delivery_manifest.json'))
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
