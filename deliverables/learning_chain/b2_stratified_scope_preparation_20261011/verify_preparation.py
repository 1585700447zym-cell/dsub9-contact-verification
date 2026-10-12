"""Fresh stdlib verification; default read-only, --seal writes this delivery seal."""
import argparse
import ast
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import subprocess
import sys

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
spec = importlib.util.spec_from_file_location('stratified_offline_analysis', OUT/'analyse_scope.py')
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)
read, sha = analysis.read, analysis.sha
checks = {}


def check(name, condition):
    checks[name] = bool(condition)
    if not condition:
        raise AssertionError(name)


def git(*args):
    return subprocess.check_output(['git',*args], cwd=ROOT)


def matrix_from_q(q):
    w,x,y,z = q
    return [[1-2*(y*y+z*z),2*(x*y-w*z),2*(x*z+w*y)],
            [2*(x*y+w*z),1-2*(x*x+z*z),2*(y*z-w*x)],
            [2*(x*z-w*y),2*(y*z+w*x),1-2*(x*x+y*y)]]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seal',action='store_true')
    args = parser.parse_args()
    binding,config = analysis.verify_sources()
    check('2254_inherited_inputs_and_runtime_verified',len(binding['files']) == 2254)
    check('18_extra_sources_verified',len(read(OUT/'source_binding.json')['extra_files']) == 18)
    check('77_previous_sealed_files_verified',len(read(analysis.PREV/'delivery_manifest.json')['files']) == 77)
    rows = analysis.cases()
    g = read(OUT/'geometry_screen.json')
    check('25_unique_5_by_5_cases_and_4_aliases',len(rows)==25)
    expected = analysis.geometry_screen(rows,config)
    check('saved_geometry_matches_fresh_recomputation',g == expected)
    check('21_new_cases_static_pass_not_dynamic_pass',all(
        r['pin_screen_passed'] and not r['actual_reset_verified'] and
        not r['actual_pure_B2_evaluation_verified'] and not r['actual_F0_F2000_evaluation_verified']
        for r in g['rows'] if not r['existing_case_id']))
    check('4_old_cases_preserve_limited_actual_evidence',sum(
        r['actual_reset_verified'] and r['actual_pure_B2_evaluation_verified'] and
        r['actual_F0_F2000_evaluation_verified'] for r in g['rows']) == 4)
    check('all_new_runtime_and_training_labels_false',all(
        r['new_runtime_scope_qualified'] is False and r['new_training_admitted'] is False for r in g['rows']))
    check('pin_hole_nominal_centers_and_dimensions_verified',len(g['pin_geometry'])==9)
    sample_count = 0
    for row in g['rows']:
        r = matrix_from_q(row['quaternion_wxyz'])
        check('quaternion_rotation_agrees_'+row['id'],max(
            abs(r[a][b]-row['rotation_Ry_Rx'][a][b]) for a in range(3) for b in range(3)) < 1e-14)
        origin = [row['x_um']*1e-6,row['y_um']*1e-6,row['start_origin_z_m']]
        for pin,detail in zip(g['pin_geometry'],row['per_pin']):
            for zsign in (-1,1):
                for index in range(32):
                    theta = index*2*math.pi/32
                    local = [pin['center_m'][0]+pin['radius_m']*math.cos(theta),
                             pin['center_m'][1]+pin['radius_m']*math.sin(theta),
                             pin['center_m'][2]+zsign*pin['half_length_m']]
                    world = [sum(r[a][k]*local[k] for k in range(3))+origin[a] for a in range(3)]
                    assert world[2] <= detail['top_z_bound_m']+1e-15
                    assert math.hypot(world[0]-pin['hole_center_m'][0],world[1]-pin['hole_center_m'][1]) <= detail['xy_radius_bound_m']+1e-15
                    sample_count += 1
    check('14400_independently_rotated_surface_samples_inside_bounds',sample_count==14400)
    aligned = next(r for r in g['rows'] if r['id']=='D00')
    check('aligned_boundary_175um_margin_and_zero_pin_top',abs(aligned['entry_margin_lower_bound_um']-175)<1e-9 and aligned['highest_pin_z_bound_um']==0)
    check('position_only_margin_matches_direct_106um_offset',all(abs(
        r['entry_margin_lower_bound_um']-(175-math.hypot(75,75)))<1e-9 for r in g['rows'] if r['group']=='position_only'))
    registry = read(OUT/'case_registry_candidate.json')
    candidate = read(OUT/'execution_candidate.json')
    digest=lambda x:hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    check('shared_common_key_preserved',registry['shared_common_key']==digest(config['common'])==config['parent_common_key'])
    check('legacy_four_case_key_preserved',registry['legacy_four_point_comparison_key']==config['common_key']==digest(dict(parent_common_key=config['parent_common_key'],cases=config['cases'])))
    check('new_matrix_scope_key_distinct_and_exact',registry['matrix_scope_key']==candidate['matrix_scope_key']==digest(dict(parent_common_key=config['parent_common_key'],cases=registry['cases'])) and registry['matrix_scope_key']!=config['common_key'])
    check('new21_order_and_four_aliases_exact',candidate['new_case_ids']==[r['id'] for r in rows if not r['existing_case_id']] and len(candidate['reused_case_aliases'])==4)
    check('case_registry_content_and_candidate_pin_exact',registry['case_metadata']==rows and len(registry['cases'])==25 and candidate['case_registry_sha256']==sha(OUT/'case_registry_candidate.json'))
    limits=candidate['limits']
    check('all_proposed_physical_limits_exact',limits==dict(dynamic_episodes=21,environment_creations=21,resets=21,control_cycles=304500,native_steps=3045000,per_episode_cycles=14500,per_episode_native_steps=145000,per_episode_wall_s=1200,whole_wall_s=21600,policy_calls=0,learner_constructions=0,tensor_loads=0,formal_updates=0,replay_publications=0,independent_tests=0))
    check('candidate_draft_no_entry_auth_or_admission',candidate['status']=='DRAFT' and all(candidate[k] is False for k in ['executable_entry_implemented','explicit_physical_authorized','scientific_execution_admitted','training_admitted','nonzero_SAC_scope_qualification_inherited']))
    check('zero_action_retries_old_budget_and_conditional_total',candidate['zero_residual']==[0.,0.,0.,0.] and candidate['retries']==0 and candidate['old_budget_closed'] is True and candidate['cumulative_before']==258 and candidate['cumulative_if_all_21_attempted']==279)
    check('42_future_frozen_actor_cells_not_admitted',candidate['deferred_frozen_actors']['F0_new_cells']==21 and candidate['deferred_frozen_actors']['F2000_new_cells']==21 and candidate['deferred_frozen_actors']['admitted'] is False)
    previous_cost=read(analysis.PREV/'assessment.json')['costs']['package_wall_s']
    check('cost_estimate_preserves_measured_basis',candidate['estimate_basis']['previous_wall_s']==previous_cost and candidate['prior_success_linear_planning_estimate_s']==previous_cost/4*21)
    check('no_new_executable_or_run_or_grant',not any((OUT/p).exists() for p in ['execution','run','baseline_entry.py','baseline_rollout.py','grant.json','authorization_request.json']))
    route=read(OUT/'route_decision.json')
    check('zero_actual_science_and_kept_stage_state',all(route[k]==0 for k in ['current_new_physical_episodes','current_new_model_constructions','current_new_policy_calls','current_new_tensors','current_new_updates','current_new_replay_publications','independent_tests']) and route['cumulative_dynamic']==258 and route['automatic_tracking']=='PAUSED' and route['full_B2_accepted'] is False and route['C_accepted'] is False)
    receipt=read(OUT/'analysis_receipt.json')
    check('no_prohibited_imports_loaded',receipt['prohibited_imports_loaded']==[] and not any(n.split('.')[0] in {'numpy','mujoco','torch','gymnasium','stable_baselines3'} for n in sys.modules))
    before=read(OUT/'before_state.json')
    check('branch_and_head_preserved',git('branch','--show-current').decode().strip()==before['branch'] and git('rev-parse','HEAD').decode().strip()==before['head'])
    check('200_shared_tool_sources_unchanged',len(before['runtime_sources'])==200 and all(sha(ROOT/p)==pin for p,pin in before['runtime_sources'].items()))
    prior=set((OUT/'git_status_before.bin').read_bytes().rstrip(b'\0').split(b'\0'))
    current=set(git('status','--porcelain=v1','-z').rstrip(b'\0').split(b'\0'))
    check('all_225_prior_dirty_entries_retained',len(prior)==225 and prior<=current)
    check('six_before_after_snapshots_and_AGENTS_preserved',len(before['documents'])==6 and all(sha(OUT/'before_documents'/p)==pin and sha(OUT/'after_documents'/p)==sha(ROOT/p) for p,pin in before['documents'].items()) and sha(ROOT/'AGENTS.md')==before['documents']['AGENTS.md'])
    docs=read(OUT/'document_update.json')['files']
    markers=[]
    for name in docs:
        text=(ROOT/name).read_text(encoding='utf-8')
        m=re.search(r'<!-- b2-scope-current -->(.*?)<!-- /b2-scope-current -->',text,re.S).group(1)
        markers.append(m.replace('../../learning_chain/','deliverables/learning_chain/'))
    check('five_current_markers_consistent',len(markers)==5 and len(set(markers))==1)
    check('accurate_scope_labels_and_C_reminder',all(s in markers[0] for s in ['B.2第3项','21个新增组合','已完成','新入口实现待开始','44.1855','累计动态258','PAUSED','完整B.2/C未验收','进入C之前','强化学习']))
    monthly=(ROOT/'deliverables/monthly_progress/2026-10/月报素材_2026-10.md').read_text(encoding='utf-8')
    heads=['## 一、本月综合摘要','## 二、关键数字与证据','## 三、负结果与限制','## 四、图表与讲稿','## 五、下一项','## 六、来源记录']
    check('monthly_five_sections_integrated',all('21' in monthly[monthly.index(a):monthly.index(b)] for a,b in zip(heads,heads[1:])))
    plan=ROOT/'docs/superpowers/plans/2026-10-11-b2-stratified-zero-baseline-entry.md'
    check('plan_snapshot_matches_and_future_task_labels',sha(plan)==sha(OUT/'入口实现计划快照.md') and '入口未实现' in plan.read_text(encoding='utf-8'))
    link_files=[OUT/'结果说明.md',plan]+[ROOT/p for p in docs]
    links=[]
    for p in link_files:
        text=p.read_text(encoding='utf-8')
        for target in re.findall(r'\]\(([^)]+)\)',text):
            if ('b2_stratified_scope_preparation_20261011' in target or 'b2-stratified-zero-baseline-entry' in target or p==OUT/'结果说明.md'):
                if not target.startswith(('http','app:','#')):
                    q=p.parent/target.split('#')[0]
                    if q.name in {'verification.json','delivery_manifest.json'} and args.seal:
                        continue
                    links.append((str(p),target,q.exists()))
    check('new_local_links_resolve',all(ok for _,_,ok in links))
    check('analysis_and_update_and_validator_syntax_valid',all(ast.parse((OUT/p).read_text(encoding='utf-8')) is not None for p in ['analyse_scope.py','update_documents.py','verify_preparation.py']))
    verification=dict(status='PASS_OFFLINE_PREPARATION_ONLY',verified_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),
        checks=checks,grouped_checks=len(checks),static_summary=g['summary'],stdlib_only=True,
        inherited_inputs_verified=2254,extra_sources_verified=18,prior_sealed_files_verified=77,
        prior_dirty_entries=225,current_dirty_entries=len(current),shared_tools_unchanged=200,
        new_physical_episodes=0,new_policy_calls=0,new_updates=0,cumulative_dynamic=258,
        independent_tests=0,full_B2_accepted=False,C_accepted=False,
        limit='only_pin_geometry_and_preparation; new_native_reset_dynamic_and_nonzero_SAC_scope_pending')
    if args.seal:
        analysis.write('verification.json',verification)
        files={str(p.relative_to(OUT)):sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='delivery_manifest.json'}
        analysis.write('delivery_manifest.json',dict(version='b2_stratified_scope_offline_delivery_v1',sealed_at=verification['verified_at'],files=files,
            source_binding_sha256=sha(OUT/'source_binding.json'),stage='B.2 item 3 offline scope preparation',
            full_B2_accepted=False,C_accepted=False,scientific_execution_admitted=False,training_admitted=False))
    elif (OUT/'delivery_manifest.json').exists():
        sealed=read(OUT/'delivery_manifest.json')['files']
        assert all(sha(OUT/p)==pin for p,pin in sealed.items()),'New delivery seal drift'
    print(json.dumps(dict(status=verification['status'],checks=len(checks),source_inputs=2254,
        static_new_cases=21,science=0,cumulative=258,seal_written=args.seal),ensure_ascii=False))


if __name__ == '__main__':
    main()
