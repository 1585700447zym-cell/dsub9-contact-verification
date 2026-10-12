"""Verify the offline review and unchanged historical evidence; no physics."""
import argparse
import ast
import json
from pathlib import Path
import re
import subprocess
import sys
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
sys.path.insert(0,str(OUT))
from analyze import read,sha,write,OLD,CORR

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--seal',action='store_true');parser.add_argument('--current-docs',action='store_true');args=parser.parse_args()
    checks=0
    def check(ok,label):
        nonlocal checks
        if not ok:raise AssertionError(label)
        checks+=1
    check(not args.seal or not (OUT/'delivery_manifest.json').exists(),'new seal')
    reg=read(OUT/'registration.json');data=read(OUT/'coverage_comparison.json');decision=read(OUT/'route_decision.json');gate=read(OUT/'recommended_gate_v2.json')
    check(reg['human_request']=='继续','authorized offline continuation')
    parent=subprocess.run([sys.executable,'-I','-X','utf8','-B',str(OLD/'verify_delivery.py')],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',check=True)
    result=json.loads(parent.stdout.strip().splitlines()[-1])
    check(result['preserved_sealed_members']==1626 and result['sealed_files']==152,'old1778 members verified')
    check(result['bound_inputs']==2516,'original bound inputs intact')
    for folder in (OLD,CORR):
        check(sha(folder/'delivery_manifest.json')==reg['parent_manifests'][folder.name],'parent manifest unchanged')
        for rel,meta in read(folder/'delivery_manifest.json')['files'].items():
            check(sha(folder/rel)==meta['sha256'] and (folder/rel).stat().st_size==meta['bytes'],'sealed parent '+rel)
    check(len(read(CORR/'delivery_manifest.json')['files'])==17,'correction17 members')
    for rel,pin in reg['source_pins'].items():check(sha(ROOT/rel)==pin,'shared runtime/source unchanged')
    old=read(OLD/'run/assessment.json');check(old['route']==data['old_route_preserved']=='INSUFFICIENT_COVERAGE_NO_EXTRA_ATTEMPTS','old failure retained')
    check(len(data['rows'])==8 and len(data['cases'])==4,'all action cases included')
    old_gaps=[];interval_gaps=[];fast_total=0;slow_total=0
    for row in data['rows']:
        receipt=read(OLD/'run'/(row['id']+'.audit.json'));a=receipt['assessment']
        check(row['archive_sha256']==receipt['archive_sha256'],'raw audit identity')
        check(row['joint_coverage']==a['joint_coverage'] and row['observation_summary']==a['observation'],'original findings retained')
        for hold,h in row['holds'].items():
            check(h['endpoint_effect_cycles']==a['joint_coverage']['hold_contact_effect_cycles'][hold],'endpoint count agrees with independent original audit')
            check(h['endpoint_effect_cycles']==len(h['endpoint_effect_ids']),'cycle evidence count')
            check(len(set(h['endpoint_effect_ids']))==len(h['endpoint_effect_ids']),'no duplicated cycles')
            check(h['endpoint_or_peak_effect_cycles']==h['endpoint_effect_cycles']+len(h['peak_only_effect_ids']),'interval union no double count')
            check(not set(h['endpoint_effect_ids'])&set(h['peak_only_effect_ids']),'endpoint and peak-only disjoint')
            check(h['next_observation_nonzero_wrench_cycles']<=h['endpoint_effect_cycles'],'feedback count bounded by actual contact/effect')
            if not h['endpoint_effect_cycles']:old_gaps.append(dict(id=row['id'],hold_cycles=int(hold)))
            if not h['endpoint_or_peak_effect_cycles']:interval_gaps.append(dict(id=row['id'],hold_cycles=int(hold)))
        fast_total+=row['holds']['1']['endpoint_effect_cycles'];slow_total+=row['holds']['50']['endpoint_effect_cycles']
    check(data['old_per_profile_endpoint_gaps']==old_gaps and len(old_gaps)==3,'all3 old gaps')
    check(data['per_profile_endpoint_or_peak_gaps']==interval_gaps==[dict(id='J02_B_CORNERS',hold_cycles=1)],'peak substitution leaves one gap')
    for case_id,case in data['cases'].items():
        rows=[r for r in data['rows'] if r['case_id']==case_id]
        check(len(rows)==2 and {r['profile'] for r in rows}=={'A_AXIS','B_CORNERS'},'same-case A/B pair only')
        check(rows[0]['initial_pose']==rows[1]['initial_pose'] and rows[0]['binding_sha256']==rows[1]['binding_sha256'],'same pose and implementation')
        for hold,h in case['holds'].items():
            check(h['endpoint_effect_cycles']==sum(r['holds'][hold]['endpoint_effect_cycles'] for r in rows),'per-case sum not cross-case substitution')
            check(h['next_observation_nonzero_wrench_cycles']==sum(r['holds'][hold]['next_observation_nonzero_wrench_cycles'] for r in rows),'feedback aggregation')
            check(h['endpoint_effect_cycles']>0 and h['next_observation_nonzero_wrench_cycles']>0,'both representative durations with observed feedback')
        for i,signs in enumerate(case['signs']):
            check(signs==sorted(set().union(*(set(r['joint_coverage']['signs'][i]) for r in rows)))==[-1,1],'all original directions retained')
        check(case['representative_coverage_observed'] and case['all_peaks_covered'],'per-case evidence complete for proposed limited purpose')
    check(fast_total==115 and slow_total==8046,'summary counts')
    check([data['cases'][k]['holds']['1']['endpoint_effect_cycles'] for k in ('J01','J02','J03','J04')]==[25,28,32,30],'case-specific fast counts')
    check(len(data['recoveries'])==4 and all(r['covered'] for r in data['recoveries']),'all4 recovery records retained')
    check(not data['recommended_per_case_endpoint_gaps'],'no per-case representative gap')
    check(decision['development_driven_post_hoc_revision'] and not decision['old_gate_regraded'],'transparent post-hoc development change')
    check(not decision['training_admitted'] and not decision['full_B2_accepted'] and not decision['C_accepted'],'no automatic qualification')
    check(gate['original_endpoint_rule_preserved'] and not gate['substep_peak_rule_used_for_qualification'] and not gate['runtime_implementation_changed'],'only aggregation-level proposal')
    check(decision['recommended_extra_coverage_episodes']==0 and decision['new_physical_attempts']==decision['new_training']==0 and decision['cumulative_dynamic']==237,'no extra physics/training cost')
    pilot=read(OUT/'pilot_preparation_scope.json')
    check(not pilot['execution_authorized'] and pilot['ordinary_SAC_only'] and pilot['new_case_matched_training'],'pilot preparation only')
    check(len(pilot['baseline_reuse_candidates'])==4,'four conditional zero-residual baseline candidates')
    for b in pilot['baseline_reuse_candidates']:check(sha(ROOT/b['file'])==b['sha256'],'baseline reuse remains source-pinned candidate')
    docs=read(OUT/'document_update.json')
    for name,pin in reg['before_documents'].items():
        check(sha(OUT/'before_documents'/name)==pin,'before document preserved')
        check(sha(OUT/'document_snapshots'/name)==docs['after_documents'][name],'after document snapshot')
        if args.current_docs:check(sha(ROOT/name)==docs['after_documents'][name],'current doc matches snapshot')
        if name!='AGENTS.md':
            t=(OUT/'document_snapshots'/name).read_text(encoding='utf-8');b=re.search(r'<!-- b2-scope-current -->(.*?)<!-- /b2-scope-current -->',t,re.S).group(1)
            check(all(s in b for s in ('B2-SCOPE-11','当前阶段B.2','237','PAUSED','训练未准入','完整B.2/C未验收')),'explicit stage and limits')
    git=lambda *a:subprocess.check_output(['git',*a],cwd=ROOT).decode('utf-8')
    check(git('branch','--show-current').strip()==reg['branch'] and git('rev-parse','HEAD').strip()==reg['head'],'same branch and HEAD')
    before=set((OUT/'git_status_before.txt').read_text(encoding='utf-8').splitlines());after=set(git('status','--porcelain=v1').splitlines())
    check(not before-after,'all prior dirty entries retained')
    for p in OUT.glob('*.py'):ast.parse(p.read_text(encoding='utf-8'));checks+=1
    check(not any(m.split('.')[0] in {'numpy','mujoco','torch','stable_baselines3'} for m in sys.modules),'stdlib verification no backend')
    result=dict(stage_id='B2-SCOPE-11',status='VERIFIED_OFFLINE_DEVELOPMENT_REVIEW',checks=checks,preserved_sealed_members=1795,
        raw_action_archives=8,fast_endpoint_effect_cycles=115,slow_endpoint_effect_cycles=8046,
        old_per_profile_gaps=3,proposed_per_case_gaps=0,recommended_extra_coverage_episodes=0,
        new_physics=0,new_training=0,cumulative_dynamic=237,training_admitted=False,full_B2_accepted=False,
        route=decision['route'],automatic_tracking='PAUSED')
    if args.seal:
        write(OUT/'verification.json',result)
        files={p.relative_to(OUT).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='delivery_manifest.json' and '__pycache__' not in p.parts}
        write(OUT/'delivery_manifest.json',dict(stage_id='B2-SCOPE-11',files=files,rolling_documents_may_advance=True))
    if (OUT/'delivery_manifest.json').exists():
        members=read(OUT/'delivery_manifest.json')['files']
        for rel,m in members.items():check(sha(OUT/rel)==m['sha256'] and (OUT/rel).stat().st_size==m['bytes'],'sealed '+rel)
        result.update(checks=checks,sealed_files=len(members),manifest_sha256=sha(OUT/'delivery_manifest.json'))
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
