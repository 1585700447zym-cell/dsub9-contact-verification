"""Read-only evidence checks; --seal writes only this new deliverable once."""
import argparse
import ast
import csv
import json
import math
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(r'D:\dsub9项目计划\first_stage_sim\.worktrees\dsub9-v1-contact-validation')
OUT=ROOT/'deliverables/learning_chain/b2_joint_learning_review_20261009'
sys.path.insert(0,str(OUT))
from analyze import SOURCE,SOURCE_PIN,read,sha

def main():
    p=argparse.ArgumentParser();p.add_argument('--seal',action='store_true');p.add_argument('--current-docs',action='store_true');args=p.parse_args()
    if args.seal:assert not (OUT/'delivery_manifest.json').exists() and not (OUT/'verification.json').exists()
    checks=0
    def check(value,label):
        nonlocal checks
        if not value:raise AssertionError(label)
        checks+=1
    def verify_manifest(folder,pin,count):
        check(sha(folder/'delivery_manifest.json')==pin,'manifest pin '+folder.name)
        members=read(folder/'delivery_manifest.json')['files'];check(len(members)==count,'member count '+folder.name)
        for rel,meta in members.items():
            check(sha(folder/rel)==meta['sha256'] and (folder/rel).stat().st_size==meta['bytes'],'preserved '+folder.name+'/'+rel)
        return len(members)
    old_members=verify_manifest(SOURCE,SOURCE_PIN,254)
    constants={}
    for node in ast.parse((SOURCE/'verify_delivery.py').read_text(encoding='utf-8')).body:
        if isinstance(node,ast.Assign):
            for target in node.targets:
                if isinstance(target,ast.Name) and target.id in ['PARENTS','HISTORICAL']:
                    constants[target.id]=ast.literal_eval(node.value)
    for kind,base in [('PARENTS',SOURCE.parent),('HISTORICAL',ROOT/'deliverables/paper_comparison')]:
        for name,pin,count in constants[kind]:old_members+=verify_manifest(base/name,pin,count)
    check(old_members==1508,'all PC06-PC14/SCOPE01-SCOPE06 members')
    binding_path=SOURCE.parent/'b2_preflight_rebound_20261008/candidate_binding.json'
    check(sha(binding_path)=='b7746e0cfaf29317c1ae692f6ed03c685d0d1a3398965c3fa36fc012b8ed3952','frozen execution binding')
    binding=read(binding_path);check(len(binding['files'])==2173,'complete input binding')
    for name,pin in binding['files'].items():check(sha(Path(name))==pin,'bound input '+name)
    for directory,expected in binding['inventories'].items():
        actual=sorted(p.relative_to(directory).as_posix() for p in Path(directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc')
        check(actual==expected,'runtime inventory '+directory)
    a=read(OUT/'analysis.json');info=read(OUT/'information_refinement.json');route=read(OUT/'route_decision.json')
    old={e['id']:e for e in read(SOURCE/'run/assessment.json')['dynamic']};episodes={e['id']:e for e in a['episodes']}
    check(set(episodes)=={f'J{i:02}_{arm}' for i in range(1,5) for arm in ['zero','script']},'exact eight inputs')
    check(a['source_manifest_sha256']==SOURCE_PIN,'source identity')
    for rel,pin in a['input_archives'].items():check(sha(ROOT/rel)==pin,'archive unchanged '+rel)
    rows_by_id={name:[] for name in episodes}
    with (OUT/'joint_cycles.csv').open(encoding='utf-8',newline='') as stream:
        for row in csv.DictReader(stream):rows_by_id[row['id']].append(row)
    for name,rows in rows_by_id.items():
        s=episodes[name];c=s['counts'];check(len(rows)==c['cycles'],'CSV episode length')
        check([int(r['cycle']) for r in rows]==list(range(len(rows))),'unbroken indices')
        check(all(math.isclose(float(r['t1_s'])-float(r['t0_s']),.002,abs_tol=1e-10) for r in rows),'control intervals')
        contact=sum(int(r['contact_after'])>0 for r in rows)
        requested=lambda r:any(float(r['request_'+k])!=0 for k in ['x','y','roll','pitch'])
        effective=lambda r:any(abs(float(r['effect_'+k]))>1e-15 for k in ['x','y','roll','pitch'])
        requests=sum(map(requested,rows));contact_effect=sum(int(r['contact_after'])>0 and effective(r) for r in rows)
        check(contact==c['contact_cycles']==old[name]['contact_cycles'],'contact counts')
        check(requests==c['script_nonzero_cycles']==old[name]['script_nonzero_cycles'],'request counts')
        check(contact_effect==c['contact_effect_cycles']==old[name]['contact_effect_cycles'],'effect counts')
        check(sum(int(r['enabled']) for r in rows)==c['permitted_cycles'],'permission counts')
        check(sum(int(r['enabled']) and int(r['contact_after'])>0 for r in rows)==c['contact_permitted_cycles'],'contact permission counts')
        check(all(not requested(r) or int(r['enabled']) for r in rows),'no masked nonzero request')
        check(sum(int(r['clipped_components']) for r in rows)==s['clipped_component_occurrences'],'CSV clipping count')
        for key,col in [('force_N','force_peak_N'),('torque_G_Nm','torque_peak_Nm')]:
            peak=s['peak_intervals'][key];row=max(rows,key=lambda r:float(r[col]))
            check(float(row[col])==peak['peak_value']==old[name]['peak_loads'][key],'peak value')
            check(float(row['t0_s'])==peak['time_s'] and float(row['t1_s'])==peak['end_time_s'],'peak interval')
        for key,peak in s['peak_intervals'].items():
            check(peak['enabled'] and not any(peak['requested']) and not any(peak['effective_command_delta']),'peak with permission and no nonzero effect '+key)
        check(s['first_contact']['enabled'] and s['first_contact']['clipped_components']==0,'first contact input facts')
        check(not s['recovery_events'] and s['outcome']['physical_stopped'],'stop distinct from recovery')
        check(math.isclose(s['force_limit_N']-s['peak_intervals']['force_N']['peak_value'],s['force_margin_N'],abs_tol=1e-15),'headroom arithmetic')
        if name.endswith('script'):
            check(len(s['pulses'])==3 and [p['cycles'] for p in s['pulses']]==[49,50,50],'three fixed pulses')
            check([p['contact_cycles'] for p in s['pulses']]==[0,50,0],'only SEARCH pulse contact')
            check(all(any(float(r['request_'+k])!=0 for r in rows) for k in ['x','y','roll','pitch']),'four requested axes')
    check(sum(len(v) for v in rows_by_id.values())==a['total_existing_cycles']==42656,'existing cycle total')
    check(info['total_vectors_checked']==42664 and info['all_eight_initial_vectors_identical'],'observation totals and initial equality')
    stall=0;stop=0;stall_contact=0
    for e in info['episodes']:
        check(e['vectors_checked']==episodes[e['id']]['counts']['cycles']+1,'all vectors including final')
        for field,f in e['clipped_fields'].items():
            check(field in ['stall_span_s[0]','hold_elapsed_s[0]'],'only observed clipped fields')
            if field=='stall_span_s[0]':
                stall+=f['occurrences'];stall_contact+=f['contact']
                check(f['permitted']==f['occurrences'] and set(f['phases'])=={'SEARCH/RUNNING'},'active clipping classification')
            else:
                stop+=f['occurrences'];check(f['permitted']==f['contact']==0 and set(f['phases'])=={'INSERT/STOPPING'},'stop clipping classification')
        check(e['clipped_occurrences']==episodes[e['id']]['clipped_component_occurrences']+1,'final hold observation accounting')
    check((stall,stall_contact,stop)==(2468,2214,3440),'clipping totals')
    for pair in info['same_time_zero_pairs']:
        check(pair['both_contact'] and pair['both_enabled'] and math.isclose(pair['same_time_s'],.324,abs_tol=1e-10),'same-time contact comparison')
        check(pair['exact_initial_equality'] and pair['precontact_max_vector_difference']<1.2e-18,'precontact numerical magnitude')
        check(not pair['sensor_noise_or_identifiability_test'],'no fitted identifiability claim')
    for pair in a['arm_pairs']:
        check(pair['identical_prefix_through_first_action_input'] and pair['prefix_input_vectors']==12,'paired prefix')
        check(not pair['causal_axis_identification'] and not pair['learned_policy_benefit_claim'],'limited effects interpretation')
        check(math.isclose(pair['task_time_delta_s'],episodes[pair['case']+'_script']['task_end_time_s']-episodes[pair['case']+'_zero']['task_end_time_s'],abs_tol=1e-12),'paired time arithmetic')
    check(route['decision']=='JOINT_CANDIDATE_PREPARATION_SUPPORTED_TRAINING_NOT_ADMITTED','route')
    check(not route['new_physical_authorization'] and not route['new_training_authorization'] and not route['training_admitted'],'no new grant')
    check(not route['full_B2_accepted'] and not route['C_accepted'] and route['automatic_tracking']=='PAUSED','scope and automation')
    check(route['cumulative_dynamic']==225 and all(route[k]==0 for k in ['new_physics','new_policy_forwards','new_updates','new_replay_publications']),'cost boundary')
    reg=read(OUT/'registration.json');update=read(OUT/'document_update.json')
    for name,pin in reg['before_documents'].items():
        check(sha(OUT/'before_documents'/name)==pin,'before snapshot '+name)
        after=OUT/'document_snapshots'/name;check(sha(after)==update['after_documents'][name],'after snapshot '+name)
        if args.current_docs:check(sha(ROOT/name)==sha(after),'rolling file equals snapshot '+name)
        if name!='AGENTS.md':
            block=re.search(r'<!-- b2-scope-current -->(.*?)<!-- /b2-scope-current -->',after.read_text(encoding='utf-8'),re.S).group(1)
            check(all(s in block for s in ['当前阶段B.2','已完成','B2-SCOPE-07','实际累计动态225','完整B.2/C未验收','2468','3440']),'current document state '+name)
    git=lambda *x:subprocess.check_output(['git',*x],cwd=ROOT)
    check(git('branch','--show-current').decode().strip()==reg['branch'],'same branch')
    check(git('rev-parse','HEAD').decode().strip()==reg['head'],'same HEAD')
    for report in ['结果说明.md','路线决定.md']:
        text=(OUT/report).read_text(encoding='utf-8')
        for link in re.findall(r'\]\(([^)]+)\)',text):
            path=(OUT/link.split('#')[0]).resolve()
            check(path.exists() or (args.seal and path==OUT/'verification.json'),'report link '+link)
    for script in OUT.glob('*.py'):ast.parse(script.read_text(encoding='utf-8'));checks+=1
    check(not any(k.split('.')[0] in {'numpy','mujoco','torch','stable_baselines3'} for k in sys.modules),'no engine or learner imports')
    result=dict(stage_id='B2-SCOPE-07',status='VERIFIED_OFFLINE_JOINT_REVIEW',checks=checks,
                preserved_sealed_members=old_members,bound_inputs=2173,existing_archives=8,existing_cycles=42656,
                observation_vectors=42664,active_search_clipped_vectors=2468,stop_clipped_vectors=3440,
                new_physics=0,new_policy_forwards=0,new_updates=0,new_replay_publications=0,cumulative_dynamic=225,
                full_B2_accepted=False,C_accepted=False,training_admitted=False,automatic_tracking='PAUSED')
    if args.seal:
        with (OUT/'verification.json').open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
        (OUT/'git_status_after.txt').write_bytes(git('-c','core.quotepath=false','status','--porcelain=v1'))
        members={p.relative_to(OUT).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(OUT.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}
        with (OUT/'delivery_manifest.json').open('x',encoding='utf-8') as f:
            json.dump(dict(stage_id='B2-SCOPE-07',status='SEALED_OFFLINE_REVIEW',user_date='2026-10-09',files=members,
                           rolling_documents='immutable snapshots; root documents may advance',training_admitted=False),f,ensure_ascii=False,indent=2);f.write('\n')
    manifest=read(OUT/'delivery_manifest.json')
    for rel,meta in manifest['files'].items():check(sha(OUT/rel)==meta['sha256'] and (OUT/rel).stat().st_size==meta['bytes'],'new sealed file '+rel)
    result.update(checks=checks,sealed_files=len(manifest['files']),manifest_sha256=sha(OUT/'delivery_manifest.json'))
    print(json.dumps(result,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
