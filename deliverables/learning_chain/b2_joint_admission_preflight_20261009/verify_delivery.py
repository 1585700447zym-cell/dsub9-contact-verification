"""Read-only candidate/delivery verification; optional one-time seal, never physics."""
import argparse
import ast
import json
from pathlib import Path
import re
import subprocess
import sys
OUT=Path(__file__).resolve().parent;sys.path.insert(0,str(OUT))
from scope_contract import ROOT,read,sha,proposal,PROPOSAL_PIN,attempt_specs
from execution_contract import write,validate_grant
from run_preflight import check_binding

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--seal',action='store_true');parser.add_argument('--current-docs',action='store_true')
    args=parser.parse_args();checks=0
    def check(condition,label):
        nonlocal checks
        if not condition:raise AssertionError(label)
        checks+=1
    if args.seal:check(not (OUT/'delivery_manifest.json').exists(),'not previously sealed')
    parent=OUT.parent/'b2_joint_admission_design_20261009';reg=read(OUT/'registration.json')
    check(sha(parent/'delivery_manifest.json')=='392b1730219968f1bee649aa4cc3077d963c2216c49ca8d5e849c2acebf6c33e','design seal pin')
    p=subprocess.run([sys.executable,'-I','-X','utf8','-B',str(parent/'verify_delivery.py')],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',check=True)
    old=json.loads(p.stdout.strip().splitlines()[-1])
    check(old['status']=='VERIFIED_ADMISSION_DESIGN_ONLY' and old['preserved_sealed_members']==1538 and old['sealed_files']==28,'1566 prior sealed members')
    for rel,meta in read(parent/'delivery_manifest.json')['files'].items():check(sha(parent/rel)==meta['sha256'],'design member '+rel)
    c,b=check_binding();request=read(OUT/'authorization_request.json')
    check(request['binding_sha256']==sha(OUT/'candidate_binding.json') and request['proposal_sha256']==PROPOSAL_PIN,'request pins')
    check(not request['explicit_user_approval'] and request['status']=='REQUESTED_NOT_AUTHORIZED','no grant')
    try:validate_grant(request,sha(OUT/'candidate_binding.json'),c)
    except ValueError:checks+=1
    else:raise AssertionError('Request accepted as grant')
    check(not (OUT/'claims').exists() and not (OUT/'grant.json').exists(),'no new physical claim/grant')
    refusal=read(OUT/'unauthorized_cli.json')
    check(refusal['status']=='PASS' and len(refusal['probes'])==2 and all(p['refused_before_claim'] and not p['output_created'] for p in refusal['probes']),'CLI rejected request and old grant')
    check(len(attempt_specs(c))==12 and c['cumulative_dynamic']==225,'fixed proposed vs actual count')
    check(c['proposed_limits']['static_attempts']==0 and c['proposed_limits']['physical_substeps_total']==1740000,'exact bounded proposal')
    design=read(parent/'admission_proposal.json')
    for key in ('action','observations','cases','attempts','engineered_recovery','coverage','stop_rules','scope'):
        check(c[key]==design[key],'unchanged reviewed design '+key)
    tests=json.loads((OUT/'offline_tests.txt').read_text(encoding='utf-8-sig').strip().splitlines()[-1])
    check(tests['status']=='PASS' and tests['failures']==tests['errors']==0 and tests['forbidden_modules']==[],'offline suite passed')
    regression=read(OUT/'real_archive_regression.json')
    check(regression['status']=='PASS_INHERITED_REAL_ARCHIVE_REGRESSION' and regression['cycles']==4834 and regression['observation_vectors']==4835,'inherited real archive regression')
    check(sha(Path(regression['source']))==regression['sha256'],'old regression input remains unchanged')
    doc=read(OUT/'document_update.json')
    for name,pin in reg['before_documents'].items():
        check(sha(OUT/'before_documents'/name)==pin,'before snapshot '+name)
        after=OUT/'document_snapshots'/name
        check(sha(after)==doc['after_documents'][name],'after snapshot '+name)
        if args.current_docs:check(sha(ROOT/name)==sha(after),'current snapshot '+name)
        if name!='AGENTS.md':
            text=after.read_text(encoding='utf-8');block=re.search(r'<!-- b2-scope-current -->(.*?)<!-- /b2-scope-current -->',text,re.S).group(1)
            check(all(s in block for s in ('B2-SCOPE-09','当前阶段B.2','已完成','实际累计动态225','未授权','完整B.2/C未验收')),'clear current status '+name)
    report=(OUT/'接入与验收说明.md').read_text(encoding='utf-8')
    check(all(s in report for s in ('未执行','未授权','225','±1.5°','固定12')),'honest delivery scope')
    git=lambda *a:subprocess.check_output(['git',*a],cwd=ROOT).decode('utf-8').strip()
    check(git('branch','--show-current')=='feature/dsub9-dynamic-actuator-v1' and git('rev-parse','HEAD')=='d2e7e4fa4ed0631d9dd1b7b98a121c1e46ea6406','same branch and HEAD')
    before=set((OUT/'git_status_before.txt').read_text(encoding='utf-8').splitlines())
    after=set(subprocess.check_output(['git','status','--porcelain=v1'],cwd=ROOT).decode('utf-8').splitlines())
    check(not before-after,'all prior uncommitted entries preserved')
    for script in OUT.glob('*.py'):ast.parse(script.read_text(encoding='utf-8'));checks+=1
    check(not any(n.split('.')[0] in {'numpy','mujoco','torch','stable_baselines3'} for n in sys.modules),'verification is standard-library only')
    review=read(OUT/'review_resolution.json')
    check(review['open_important_findings']==0,'review issues resolved')
    for name,pin in review['reviewed_core'].items():check(sha(OUT/name)==pin,'reviewed core unchanged '+name)
    result=dict(stage_id='B2-SCOPE-09',status='VERIFIED_IMPLEMENTATION_OFFLINE_ONLY',checks=checks,
        offline_tests=tests['tests'],preserved_sealed_members=1566,bound_inputs=len(b['files']),new_physics=0,
        new_environment_creations=0,new_resets=0,new_learner_constructions=0,new_tensor_reads=0,new_policy_forwards=0,
        new_updates=0,new_replay_publications=0,cumulative_dynamic=225,proposed_max_dynamic=12,
        proposal_authorized=False,runner_implemented=True,training_admitted=False,full_B2_accepted=False,C_accepted=False,automatic_tracking='PAUSED')
    if args.seal:
        write(OUT/'verification.json',result)
        files={p.relative_to(OUT).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(OUT.rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc' and p.name!='delivery_manifest.json'}
        write(OUT/'delivery_manifest.json',dict(stage_id='B2-SCOPE-09',files=files,rolling_documents_may_advance=True))
    if (OUT/'delivery_manifest.json').exists():
        members=read(OUT/'delivery_manifest.json')['files']
        for rel,meta in members.items():check(sha(OUT/rel)==meta['sha256'] and (OUT/rel).stat().st_size==meta['bytes'],'sealed '+rel)
        result.update(checks=checks,sealed_files=len(members),manifest_sha256=sha(OUT/'delivery_manifest.json'))
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
