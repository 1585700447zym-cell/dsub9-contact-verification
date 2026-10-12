"""Fresh pure verification, immutable document snapshots and delivery seal."""
import argparse
import ast
from pathlib import Path
import re
import subprocess
import sys
OUT=Path(__file__).resolve().parent;sys.path.insert(0,str(OUT))
from joint_contract import ROOT,read,write,sha,digest,LIMITS,learning_config
from execution import verify_sources
from prepare import adapters
from freeze_inputs import supervision_sources


def main():
    p=argparse.ArgumentParser();p.add_argument('--seal',action='store_true');p.add_argument('--current-docs',action='store_true');args=p.parse_args()
    if args.seal and (OUT/'delivery_manifest.json').exists():raise PermissionError('Never reseal old evidence')
    results=[]
    for test in sorted(OUT.glob('test_*.py')):
        proc=subprocess.run([sys.executable,'-I','-X','utf8','-B',str(test)],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
        if proc.returncode:raise RuntimeError(proc.stdout+proc.stderr)
        n=int(re.search(r'Ran (\d+) tests?',proc.stderr).group(1))
        results.append(dict(file=test.name,count=n,exit_code=0,output=proc.stdout+proc.stderr))
    for name,text in {**adapters()[0],**supervision_sources()}.items():
        if (OUT/name).read_text(encoding='utf-8')!=text:raise ValueError('Generated adaptation drift: '+name)
    for path in OUT.glob('*.py'):ast.parse(path.read_text(encoding='utf-8'))
    binding=read(OUT/'source_binding.json');verify_sources(binding)
    candidate=read(OUT/'candidate.json');request=read(OUT/'authorization_request.json')
    assert candidate['limits']==LIMITS and candidate['learning_config_sha256']==digest(learning_config())
    assert candidate['primary_metric']['failure_penalty_s']==read(OUT/'configuration.json')['common']['failure_penalty_s']==26
    assert request['status']=='UNAPPROVED' and request['explicit_user_authorized'] is False and not candidate['training_admitted']
    assert request['binding_sha256']==sha(OUT/'source_binding.json') and request['candidate_sha256']==digest(candidate)
    assert not (OUT/'future_claims').exists()
    parent=OUT.parent/'b2_joint_coverage_review_20261009'
    reg=read(OUT/'registration.json');assert sha(parent/'delivery_manifest.json')==reg['parent_manifest_sha256']
    proc=subprocess.run([sys.executable,'-I','-X','utf8','-B',str(parent/'verify_delivery.py')],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',check=True)
    prior=__import__('json').loads(proc.stdout.strip().splitlines()[-1]);assert prior['preserved_sealed_members']+prior['sealed_files']==1822
    baseline=read(OUT/'baseline_equivalence.json');assert len(baseline['rows'])==4
    for row in baseline['rows']:assert sha(ROOT/row['archive'])==row['archive_sha256']
    review=read(OUT/'review_resolution.json');assert review['unresolved_critical']==review['unresolved_important']==0
    docs=read(OUT/'document_update.json')
    for name,pin in reg['before_documents'].items():
        assert sha(OUT/'before_documents'/name)==pin
        assert sha(OUT/'document_snapshots'/name)==docs['after_documents'][name]
        if args.current_docs:assert sha(ROOT/name)==docs['after_documents'][name]
    git=lambda *a:subprocess.check_output(['git',*a],cwd=ROOT).decode('utf-8')
    assert git('branch','--show-current').strip()==reg['branch'] and git('rev-parse','HEAD').strip()==reg['head']
    before=set((OUT/'git_status_before.txt').read_text(encoding='utf-8').splitlines());after=set(git('status','--porcelain=v1').splitlines())
    assert not before-after,'Prior dirty entries lost'
    assert not any(k.split('.')[0] in {'numpy','torch','mujoco','stable_baselines3'} for k in sys.modules)
    result=dict(stage_id='B2-SCOPE-12',status='OFFLINE_INTEGRATION_CANDIDATE_VERIFIED',unit_checks=sum(r['count'] for r in results),
        old_sealed_members_preserved=1822,bound_inputs=len(binding['files']),real_baseline_archives=4,new_physics=0,
        learner_constructions=0,tensor_loads=0,network_forwards=0,formal_updates=0,replay_publications=0,
        cumulative_dynamic=237,training_admitted=False,full_B2_accepted=False,C_accepted=False,automatic_tracking='PAUSED',
        proposed_dynamic=17,proposed_formal_updates=2000)
    if args.seal:
        write(OUT/'offline_tests.json',dict(results=results,total=sum(r['count'] for r in results),backend_imports=0))
        write(OUT/'prior_verification.json',prior);write(OUT/'verification.json',result)
        (OUT/'git_status_after.txt').write_text(git('status','--porcelain=v1'),encoding='utf-8')
        files={p.relative_to(OUT).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='delivery_manifest.json' and '__pycache__' not in p.parts}
        write(OUT/'delivery_manifest.json',dict(stage_id='B2-SCOPE-12',files=files,rolling_documents_may_advance=True))
    if (OUT/'delivery_manifest.json').exists():
        for rel,meta in read(OUT/'delivery_manifest.json')['files'].items():assert sha(OUT/rel)==meta['sha256'] and (OUT/rel).stat().st_size==meta['bytes']
        result.update(sealed_files=len(read(OUT/'delivery_manifest.json')['files']),manifest_sha256=sha(OUT/'delivery_manifest.json'))
    print(__import__('json').dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
