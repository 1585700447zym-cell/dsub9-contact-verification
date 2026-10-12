"""Validate design consistency and historical preservation; no dynamic backend."""
import argparse
import ast
import itertools
import json
import math
from pathlib import Path
import re
import subprocess
import sys

OUT=Path(r'D:\dsub9项目计划\first_stage_sim\.worktrees\dsub9-v1-contact-validation\deliverables\learning_chain\b2_joint_admission_design_20261009')
sys.path.insert(0,str(OUT))
from review_evidence import ROOT,PARENT,DOCS,read,sha

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--seal',action='store_true');parser.add_argument('--current-docs',action='store_true');args=parser.parse_args()
    if args.seal:assert not (OUT/'delivery_manifest.json').exists() and not (OUT/'verification.json').exists()
    count=0
    def check(v,label):
        nonlocal count
        if not v:raise AssertionError(label)
        count+=1
    check(sha(PARENT/'delivery_manifest.json')=='ef538c8951829a6a1d07cf005134b8ee26788f3a0e40a688dbdfd2c08c83af54','parent manifest pin')
    parent_manifest=read(PARENT/'delivery_manifest.json')
    for rel,meta in parent_manifest['files'].items():check(sha(PARENT/rel)==meta['sha256'],'parent member '+rel)
    # Parent verifier is pinned above, supports rolling roots advancing, and only
    # reads sealed evidence. Its own source contains no execution/learning path.
    completed=subprocess.run([sys.executable,'-I','-X','utf8','-B',str(PARENT/'verify_delivery.py')],cwd=ROOT,
                             capture_output=True,text=True,encoding='utf-8',check=True)
    parent_result=json.loads(completed.stdout.strip().splitlines()[-1])
    check(parent_result['status']=='VERIFIED_OFFLINE_JOINT_REVIEW','read-only inherited verification')
    check(parent_result['preserved_sealed_members']==1508 and parent_result['sealed_files']==30,'1538 preserved old members')
    check(parent_result['bound_inputs']==2173,'inherited execution source binding')
    for rel,pin in read(OUT/'review_source_bindings.json').items():check(sha(ROOT/rel)==pin,'new review input '+rel)
    e=read(OUT/'evidence_review.json');p=read(OUT/'admission_proposal.json');cost=read(OUT/'cost_basis.json')
    check(e['total_cycles']==42656 and e['clipped_search_vectors']==2468,'existing archive accounting')
    check(len(e['episodes'])==8,'eight joint archives')
    for row in e['episodes']:
        check(row['search_history_frozen'] and row['search_timing_fields_unsaturated'],'retained history and live timers')
        check(row['max_active_insert_stall_span_s']<.403,'active insert span')
        check(len(row['return_insert'])==1 and row['return_insert'][0]['history_empty'] and row['return_insert'][0]['stall_span_s']==0,'clear before INSERT')
    check(e['semantic_decision']=='NO_OBSERVATION_CHANGE_REQUIRED_BY_THIS_CLIPPING_FINDING','semantic decision')
    recovery=e['natural_recovery']
    check(recovery['observed_retraction_control_boundary_m']>=.0002 and recovery['all_masked_recovery_cycles']==297,'existing real recovery')
    check(recovery['nonzero_requests_during_recovery']==0 and not recovery['joint_initial_pose_covered'],'no inflated recovery coverage')
    check(recovery['outcome']['task_outcome']=='TASK_FAILURE' and recovery['outcome']['physical_stopped'],'old G failure retained')
    tests=e['historical_test_evidence'];check(len(tests)==31 and all(t['passed'] for t in tests),'historical XML record count')
    check(sum(t['current_source_qualification'] for t in tests)==22,'current vs historical test classification')
    check(p['status']=='DESIGNED_NOT_IMPLEMENTED_NOT_AUTHORIZED' and not p['runner_implemented'],'design is not implementation')
    check(not any(p[k] for k in ['static_authorized','dynamic_authorized','training_admitted']),'no execution or training grant')
    check(p['actual_new_dynamic']==p['actual_new_updates']==0 and p['current_cumulative_dynamic']==225,'actual cost unchanged')
    check(p['proposed_max_new_dynamic']==len(p['attempts'])==12 and p['proposed_cumulative_ceiling_if_separately_approved']==237,'proposal count')
    check(p['proposed_separate_static_attempts']==0 and p['proposed_environment_creations']==p['proposed_resets']==12,'reset budget explicit')
    check(p['proposed_max_cycles_total']==12*p['proposed_max_cycles_per_attempt']==174000,'cycle ceiling')
    check(p['proposed_max_native_steps_total']==12*p['proposed_max_native_steps_per_attempt']==1740000,'substep ceiling')
    check(all(p[k]==0 for k in ['proposed_training_updates','proposed_network_forwards','proposed_replay_publications','proposed_learner_constructions','proposed_tensor_reads']),'all learning costs excluded')
    check(p['action']['physical_scale']==[50e-6,50e-6,.0005,.0005] and p['action']['normalized_bounds']==[-1,1],'unchanged F50 scale')
    check(p['observations']['width']==137 and not p['observations']['normalization_changed'] and not p['action']['case_labels_used_for_action'],'unchanged observation and no case oracle')
    cases=p['cases'];check([c['id'] for c in cases]==['J01','J02','J03','J04'],'only four original joint points')
    for c in cases:
        check(abs(c['x_um'])==abs(c['y_um'])==75 and abs(c['roll_deg'])==abs(c['pitch_deg'])==.25,'fixed joint offsets')
        check(c['yaw_deg']==0 and c['start_origin_z_m']==-.004 and c['target_depth_m']==.004 and 'script_sign' not in c,'fixed remaining pose and no action oracle')
    A,B=p['action']['profiles'];basis=[]
    for axis in range(4):
        for sign in [1,-1]:
            v=[0]*4;v[axis]=sign;basis.append(v)
    check(A['patterns']==basis,'eight signed basis directions')
    check(B['patterns']==list(map(list,itertools.product([-1,1],repeat=4))),'16 exact corners')
    for profile in [A,B]:
        check([b['hold_cycles'] for b in profile['blocks']]==[50,1],'100ms and 2ms blocks')
        check(len(profile['patterns'])*51==profile['block_cycles'],'pattern period')
    expected=[c['id']+'_'+k for k in ['A_AXIS','B_CORNERS','R_RECOVERY'] for c in cases]
    check([a['id'] for a in p['attempts']]==expected and len(set(expected))==12,'one-shot immutable order')
    r=p['engineered_recovery']
    check(not r['physics_state_overwritten'] and not r['controller_or_guard_thresholds_changed'] and not r['natural_task_success_claim'] and not r['learning_data_eligible'],'engineering fixture scope')
    check(r['original_recovery_count_limit']==1 and r['require_measured_actual_retraction_m']==.0002,'unchanged recovery minimum')
    check(r['masked_interval_request']==[1,-1,1,-1] and r['require_second_search'],'nonzero mask challenge')
    check(not p['stop_rules']['retry_allowed'] and p['stop_rules']['unused_allowance_closed'],'closed finite proposal')
    check(not p['scope']['full_B2_accepted'] and not p['scope']['C_accepted'] and not p['scope']['old_budgets_reopened'],'no full scope acceptance')
    check(cost==p['cost'],'identical cost basis')
    wall=sum(row['existing_wall_seconds'] for row in e['episodes'])
    check(math.isclose(cost['recorded_worker_wall_seconds'],wall,abs_tol=1e-9),'observed cost total')
    check(math.isclose(cost['observed_worker_seconds_per_cycle'],wall/42656,abs_tol=1e-12),'cost rate')
    check(math.isclose(cost['mean_episode_extrapolation_for_12_s'],wall*1.5,abs_tol=1e-8),'mean cost forecast')
    check(math.isclose(cost['max_cycle_extrapolation_for_174000_s'],wall/42656*174000,abs_tol=1e-8),'cap cost forecast')
    check(cost['proposed_whole_wall_limit_s']==21600 and cost['proposed_per_attempt_wall_limit_s']==1200,'proposed wall caps')
    matrix=read(OUT/'inheritance_matrix.json');check(len(matrix)==8 and len({r['id'] for r in matrix})==8,'inheritance mapping')
    reg=read(OUT/'registration.json');doc=read(OUT/'document_update.json')
    for name in DOCS:
        check(sha(OUT/'before_documents'/name)==reg['before_documents'][name],'before snapshot '+name)
        after=OUT/'document_snapshots'/name;check(sha(after)==doc['after_documents'][name],'after snapshot '+name)
        if args.current_docs:check(sha(ROOT/name)==sha(after),'current doc snapshot '+name)
        if name!='AGENTS.md':
            block=re.search(r'<!-- b2-scope-current -->(.*?)<!-- /b2-scope-current -->',after.read_text(encoding='utf-8'),re.S).group(1)
            check(all(k in block for k in ['当前阶段B.2','已完成','B2-SCOPE-08','实际累计动态225','未实施、未授权','完整B.2/C未验收']),'accurate current stage '+name)
    report=(OUT/'准入方案.md').read_text(encoding='utf-8')
    check(all(s in report for s in ['预检程序尚未实现','没有执行授权','不是当前累计']),'unambiguous proposal status')
    check(not any(word in report for word in ['TODO','TBD','待定']),'no unfilled specification markers')
    for link in re.findall(r'\]\(([^)]+)\)',report):
        target=(OUT/link.split('#')[0]).resolve()
        check(target.exists() or (args.seal and target==OUT/'verification.json'),'report link '+link)
    git=lambda *a:subprocess.check_output(['git',*a],cwd=ROOT)
    check(git('branch','--show-current').decode().strip()==reg['branch'] and git('rev-parse','HEAD').decode().strip()==reg['head'],'same branch and HEAD')
    original=set((OUT/'git_status_before.txt').read_text(encoding='utf-8').splitlines())
    check(not original-set(git('-c','core.quotepath=false','status','--porcelain=v1').decode('utf-8').splitlines()),'all prior dirty status entries preserved')
    for script in OUT.glob('*.py'):ast.parse(script.read_text(encoding='utf-8'));count+=1
    check(not any(n.split('.')[0] in ['numpy','mujoco','torch','stable_baselines3'] for n in sys.modules),'standard library only')
    result=dict(stage_id='B2-SCOPE-08',status='VERIFIED_ADMISSION_DESIGN_ONLY',checks=count,
                parent_verification=parent_result,preserved_sealed_members=1538,bound_inputs=2173,
                existing_cycles=42656,historical_test_records=31,new_physics=0,new_learner_constructions=0,
                new_tensor_reads=0,new_policy_forwards=0,new_updates=0,new_replay_publications=0,
                cumulative_dynamic=225,proposed_max_dynamic=12,proposal_authorized=False,runner_implemented=False,
                training_admitted=False,full_B2_accepted=False,C_accepted=False,automatic_tracking='PAUSED')
    if args.seal:
        with (OUT/'verification.json').open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
        (OUT/'git_status_after.txt').write_bytes(git('-c','core.quotepath=false','status','--porcelain=v1'))
        files={p.relative_to(OUT).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(OUT.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}
        with (OUT/'delivery_manifest.json').open('x',encoding='utf-8') as f:json.dump(dict(stage_id='B2-SCOPE-08',status='SEALED_DESIGN_ONLY',files=files,
             user_date='2026-10-09',rolling_documents='snapshots immutable; roots may advance',dynamic_authorized=False,training_admitted=False),f,ensure_ascii=False,indent=2);f.write('\n')
    manifest=read(OUT/'delivery_manifest.json')
    for rel,meta in manifest['files'].items():check(sha(OUT/rel)==meta['sha256'] and (OUT/rel).stat().st_size==meta['bytes'],'new member '+rel)
    print(json.dumps(dict(status=result['status'],checks=count,sealed_files=len(manifest['files']),manifest_sha256=sha(OUT/'delivery_manifest.json'),
         preserved_sealed_members=1538,bound_inputs=2173,actual_cumulative=225,proposed_dynamic=12,proposal_authorized=False),ensure_ascii=False),flush=True)

if __name__=='__main__':main()
