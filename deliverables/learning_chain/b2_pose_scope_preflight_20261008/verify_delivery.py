"""Verify/seal the offline delivery, not the physical scope. Standard library only."""
import argparse
import ast
import json
from pathlib import Path
import re
import sys

OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT))
from scope_contract import ROOT,proposal,read,sha,PROPOSAL_PIN
from execution_contract import write
from run_preflight import check_binding,BINDING
from update_documents import DOCS,PLAN


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--seal',action='store_true')
    parser.add_argument('--current-docs',action='store_true');args=parser.parse_args()
    if args.seal and (OUT/'delivery_manifest.json').exists():raise FileExistsError('Already sealed')
    c,b=check_binding();checks=0
    def check(value,label):
        nonlocal checks
        if not value:raise AssertionError(label)
        checks+=1
    check(c['cumulative_dynamic']==208 and c['automatic_tracking']=='PAUSED','Current physical count')
    request=read(OUT/'authorization_request.json')
    check(request['explicit_user_approval'] is False and request['status']=='REQUESTED_NOT_AUTHORIZED','No grant issued')
    check(request['binding_sha256']==sha(BINDING) and request['limits']==c['proposed_limits'],'Concrete request binding')
    check(request['proposal_sha256']==PROPOSAL_PIN,'Original proposal')
    tests=read(OUT/'offline_tests.json')
    check(tests['passed'] and tests['engine_imports']==[],'Complete offline checks')
    check(tests['existing_parent_tests']==12,'Existing pure regressions')
    for name,pin in tests['log_sha256'].items():check(sha(OUT/name)==pin,'Test evidence '+name)
    review=(OUT/'review.md').read_text(encoding='utf-8')
    check('Final disposition: OFFLINE_IMPLEMENTATION_READY' in review,'Review author disposition')
    for p in OUT.glob('*.py'):
        ast.parse(p.read_text(encoding='utf-8-sig'),filename=str(p));checks+=1
    scope=OUT.parent/'b2_scope_audit_20261008'
    check(sha(scope/'delivery_manifest.json')=='f0ece40fc2fc3ab83b99506bb13a59158dc0282fe674dbaf03b3f5b7e47e0576','Scope plan seal')
    for name,item in read(scope/'delivery_manifest.json')['files'].items():
        check(sha(scope/name)==item['sha256'] and (scope/name).stat().st_size==item['bytes'],'Scope plan member '+name)
    for name in DOCS+[PLAN]:
        before=OUT/'before_documents'/name;snap=OUT/'document_snapshots'/name
        check(before.is_file() and snap.is_file(),'Snapshots '+name)
        if args.current_docs:check((ROOT/name).read_bytes()==snap.read_bytes(),'Current document '+name)
        if name!=PLAN:
            text=snap.read_text(encoding='utf-8')
            check('B2-SCOPE-02' in text and '完整B.2/C未验收' in text,'Current scope boundary '+name)
    plan=(OUT/'document_snapshots'/PLAN).read_text(encoding='utf-8')
    check('- [ ] 获得该具体新物理授权' in plan and '- [x]' in plan,'Offline/physical steps separate')
    for file in [OUT/'结果说明.md',OUT/'review.md']:
        for target in re.findall(r'\]\(([^)]+)\)',file.read_text(encoding='utf-8')):
            if not target.startswith(('http:','https:','#')):
                check((file.parent/target.split('#')[0]).resolve().exists(),'Report link '+target)
    check(not any(k.split('.')[0] in {'mujoco','torch','numpy','stable_baselines3','gymnasium'} for k in sys.modules),'Verifier imports no numerical runtime')
    if args.seal:
        check(not (OUT/'claims').exists(),'No physical claim created at preparation')
        result=dict(status='OFFLINE_IMPLEMENTATION_VERIFIED',user_date='2026-10-08',assertions=checks,
            bound_files=len(b['files']),new_tests=tests['new_tests'],existing_parent_tests=12,
            old_scope_members=19,prior_evidence=read(OUT/'prior_verification.json'),
            actual_new=dict(engine_loads=0,static_initializations=0,dynamic_attempts=0,physical_substeps=0,
                network_forwards=0,tensor_reads=0,optimizer_updates=0,replay_publications=0),
            cumulative_dynamic=208,automatic_tracking='PAUSED',full_B2_accepted=False,C_accepted=False,
            physical_execution_authorized=False,training_admitted=False)
        write(OUT/'verification.json',result)
        members={p.relative_to(OUT).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size)
            for p in sorted(OUT.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}
        manifest=dict(status='SEALED_OFFLINE_SCOPE_IMPLEMENTATION',user_date='2026-10-08',files=members,
            physical_execution_authorized=False,training_admitted=False,rolling_documents='immutable snapshots')
        with (OUT/'delivery_manifest.json').open('x',encoding='utf-8',newline='\n') as f:
            json.dump(manifest,f,ensure_ascii=False,indent=2);f.write('\n')
    manifest=read(OUT/'delivery_manifest.json')
    for name,item in manifest['files'].items():
        check(sha(OUT/name)==item['sha256'] and (OUT/name).stat().st_size==item['bytes'],'Delivery member '+name)
    print(json.dumps(dict(status='VERIFIED_OFFLINE_SCOPE_IMPLEMENTATION',assertions=checks,
        bound_files=len(b['files']),sealed_files=len(manifest['files']),manifest_sha256=sha(OUT/'delivery_manifest.json'),
        binding_sha256=sha(BINDING),new_physical=0,new_training=0,cumulative_dynamic=208),ensure_ascii=False))


if __name__=='__main__':main()
