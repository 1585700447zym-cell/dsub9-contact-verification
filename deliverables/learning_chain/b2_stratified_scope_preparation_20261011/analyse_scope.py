"""Reproduce the offline scope screen and a DRAFT cost proposal; no science runtime.

This script never creates a simulator, policy, training job or execution grant.
It reads frozen inputs and writes only analysis artifacts in its own directory.
"""
import csv
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.abc
import importlib.util
import json
import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


class NoScience(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'numpy', 'mujoco', 'torch', 'gymnasium', 'stable_baselines3'}:
            raise ImportError('Offline scope screen forbids scientific imports: ' + fullname)


sys.meta_path.insert(0, NoScience())
OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
BASE = ROOT / 'deliverables/learning_chain'
PREP = BASE / 'b2_pure_baseline_preparation_20261011'
PREV = BASE / 'b2_pure_baseline_execution_20261011'
DESIGN = BASE / 'b2_stratified_evaluation_design_20261011'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''):
            h.update(chunk)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                     sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')


def cases():
    with (DESIGN / 'scenario_matrix.csv').open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        for key in ('x_um', 'y_um', 'roll_deg', 'pitch_deg', 'yaw_deg',
                    'start_origin_z_m', 'target_depth_m'):
            row[key] = float(row[key])
    assert len(rows) == 25 and len({r['id'] for r in rows}) == 25
    assert Counter(r['group'] for r in rows) == dict(aligned=1, position_only=4,
                                                   orientation_only=4, joint=16)
    positions = {(0., 0.), (75., 75.), (-75., 75.), (-75., -75.), (75., -75.)}
    angles = {(0., 0.), (.25, .25), (-.25, .25), (-.25, -.25), (.25, -.25)}
    assert {(r['x_um'], r['y_um'], r['roll_deg'], r['pitch_deg']) for r in rows} == {
        (x, y, roll, pitch) for x, y in positions for roll, pitch in angles}
    assert all(r['yaw_deg'] == 0 and r['start_origin_z_m'] == -.004 and
               r['target_depth_m'] == .004 and r['data_use'] == 'development' for r in rows)
    old = read(PREP / 'configuration.json')['cases']
    for row in rows:
        if row['existing_case_id']:
            original = next(c for c in old if c['id'] == row['existing_case_id'])
            assert all(row[k] == v for k, v in original.items() if k != 'id')
    assert {r['id']: r['existing_case_id'] for r in rows if r['existing_case_id']} == {
        'J11': 'J01', 'J22': 'J02', 'J33': 'J03', 'J44': 'J04'}
    return rows


def verify_sources():
    b = read(OUT / 'source_binding.json')
    for p, pin in b['extra_files'].items():
        assert sha(ROOT / p) == pin, p
    seal = read(PREV / 'delivery_manifest.json')
    for p, pin in seal['files'].items():
        assert sha(PREV / p) == pin, p
    spec = importlib.util.spec_from_file_location('scope_old_contract', PREP / 'contract.py')
    contract = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(contract)
    source, config = contract.verify_binding()
    assert len(source['files']) == 2254 and len(seal['files']) == 77
    assert config['parent_common_key'] == contract.digest(config['common'])
    assert config['common_key'] == contract.digest(dict(
        parent_common_key=config['parent_common_key'], cases=config['cases']))
    return source, config


def geometry_screen(rows, config):
    model = ET.parse(PREP / 'model.xml').getroot()
    male = model.find("./worldbody/body[@name='male']")
    female = model.find("./worldbody/body[@name='female']")
    assert all(b.get('pos') is None and b.get('quat') is None for b in (male, female))
    pins = male.findall("./geom[@class='pin_collision']")
    assert len(pins) == 9
    pin_inputs = []
    for index, pin in enumerate(pins, 1):
        assert pin.get('type') == 'cylinder' and pin.get('quat') is None
        center = list(map(float, pin.get('pos').split()))
        radius, half = map(float, pin.get('size').split())
        hole = female.find("./geom[@name='hole_convex256_%02d_entry_000']" % index)
        hole_xyz = list(map(float, hole.get('pos').split()))
        assert center[:2] == hole_xyz[:2] and hole_xyz[2] == 0
        assert radius == .0005 and half == .002 and center[2] == .002
        pin_inputs.append(dict(name=pin.get('name'), center_m=center,
                               hole_center_m=hole_xyz, radius_m=radius, half_length_m=half))
    referee = config['common']['geometry_referee']
    entry, main = referee['layers']
    assert entry['name'] == 'entry' and main['name'] == 'main'
    assert entry['z0_m'] == 0 and entry['z1_m'] == main['z0_m']
    details = []
    for row in rows:
        r, p = math.radians(row['roll_deg']), math.radians(row['pitch_deg'])
        cr, sr, cp, sp = math.cos(r), math.sin(r), math.cos(p), math.sin(p)
        rotation = [[cp, sp*sr, sp*cr], [0., cr, -sr], [-sp, cp*sr, cp*cr]]
        quaternion = [math.cos(p/2)*math.cos(r/2), math.cos(p/2)*math.sin(r/2),
                      math.sin(p/2)*math.cos(r/2), -math.sin(p/2)*math.sin(r/2)]
        assert abs(sum(q*q for q in quaternion) - 1) < 1e-14
        assert all(abs(sum(rotation[a][k]*rotation[b][k] for k in range(3)) - (a == b))
                   < 1e-14 for a in range(3) for b in range(3))
        origin = [row['x_um']*1e-6, row['y_um']*1e-6, row['start_origin_z_m']]
        per_pin = []
        for pin in pin_inputs:
            center = [sum(rotation[a][k]*pin['center_m'][k] for k in range(3)) + origin[a]
                      for a in range(3)]
            top = (center[2] + pin['half_length_m']*abs(rotation[2][2]) +
                   pin['radius_m']*math.hypot(rotation[2][0], rotation[2][1]))
            projected_bound = (math.hypot(center[0]-pin['hole_center_m'][0],
                                          center[1]-pin['hole_center_m'][1]) +
                               pin['half_length_m']*math.hypot(rotation[0][2], rotation[1][2]) +
                               pin['radius_m'])
            per_pin.append(dict(pin=pin['name'], transformed_center_m=center,
                                top_z_bound_m=top, xy_radius_bound_m=projected_bound,
                                entry_margin_lower_bound_m=entry['radius_m']-projected_bound))
        margin = min(x['entry_margin_lower_bound_m'] for x in per_pin)
        top = max(x['top_z_bound_m'] for x in per_pin)
        guard_ok = max(abs(r), abs(p)) <= config['common']['guard_config']['initial_roll_pitch_limit_rad']
        passed = margin > 0 and top < main['z0_m'] and guard_ok and rotation[2][2] >= referee['minimum_axis_z']
        details.append(dict(**row, quaternion_wxyz=quaternion, rotation_Ry_Rx=rotation,
                            pin_screen_passed=passed, entry_margin_lower_bound_um=margin*1e6,
                            highest_pin_z_bound_um=top*1e6,
                            gap_to_main_lower_bound_um=(main['z0_m']-top)*1e6,
                            initial_component_guard_passed=guard_ok, pin_axis_z=rotation[2][2],
                            per_pin=per_pin,
                            actual_reset_verified=bool(row['existing_case_id']),
                            actual_pure_B2_evaluation_verified=bool(row['existing_case_id']),
                            actual_F0_F2000_evaluation_verified=bool(row['existing_case_id']),
                            new_runtime_scope_qualified=False, new_training_admitted=False))
    assert all(d['pin_screen_passed'] for d in details)
    return dict(version='entry_cylinder_projection_screen_v1', scope='offline_pin_geometry_only',
                source_binding_sha256=sha(OUT / 'source_binding.json'),
                shared_common_key=config['parent_common_key'],
                legacy_four_point_comparison_key=config['common_key'],
                formulas=dict(rotation='Ry(pitch) Rx(roll), yaw=0',
                              top='c_z + half_length*abs(R_zz) + radius*hypot(R_zx,R_zy)',
                              xy='norm(c_xy-hole_xy) + half_length*hypot(R_xz,R_yz) + radius',
                              entry_margin_lower_bound='entry_radius - xy'),
                excludes=['native_MuJoCo_reset', 'full_guide_shell_collisions', 'initial_wrench_penetration',
                          'dynamic_trajectory', 'nonzero_policy_actions', 'continuous_domain_qualification'],
                pin_geometry=pin_inputs, referee=referee, rows=details,
                summary=dict(total=25, new=21, old=4, passed=25,
                             minimum_entry_margin_lower_bound_um=min(d['entry_margin_lower_bound_um'] for d in details),
                             maximum_pin_top_bound_um=max(d['highest_pin_z_bound_um'] for d in details),
                             minimum_main_gap_lower_bound_um=min(d['gap_to_main_lower_bound_um'] for d in details)))


def main():
    source, config = verify_sources()
    rows = cases()
    result = geometry_screen(rows, config)
    write('geometry_screen.json', result)
    columns = ['id', 'group', 'x_um', 'y_um', 'roll_deg', 'pitch_deg', 'existing_case_id',
               'pin_screen_passed', 'entry_margin_lower_bound_um', 'highest_pin_z_bound_um',
               'gap_to_main_lower_bound_um', 'actual_reset_verified',
               'actual_pure_B2_evaluation_verified', 'actual_F0_F2000_evaluation_verified',
               'new_runtime_scope_qualified', 'new_training_admitted']
    with (OUT / 'qualification_matrix.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction='ignore')
        writer.writeheader(); writer.writerows(result['rows'])
    actual_cases = [{k: r[k] for k in ('id','x_um','y_um','roll_deg','pitch_deg','yaw_deg',
                                      'start_origin_z_m','target_depth_m')} for r in rows]
    matrix_scope_key = hashlib.sha256(json.dumps(dict(
        parent_common_key=config['parent_common_key'], cases=actual_cases),
        ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    registry = dict(version='b2_25_development_registry_draft_v1',
                    shared_common_key=config['parent_common_key'],
                    legacy_four_point_comparison_key=config['common_key'],
                    matrix_scope_key=matrix_scope_key,
                    source_matrix_sha256=sha(DESIGN / 'scenario_matrix.csv'), cases=actual_cases,
                    case_metadata=rows,
                    actual_scope_uses_registry_not_legacy_common_cases=True,
                    historical_common_object_unchanged=True, scientific_execution_admitted=False,
                    training_admitted=False)
    write('case_registry_candidate.json', registry)
    costs = read(PREV / 'assessment.json')['costs']
    candidate = dict(version='b2_21_zero_baseline_package_proposal_v1', status='DRAFT',
                     executable_entry_implemented=False, explicit_physical_authorized=False,
                     scientific_execution_admitted=False, training_admitted=False,
                     method='pure_B2_zero_residual_same_common_session',
                     shared_common_key=config['parent_common_key'], matrix_scope_key=matrix_scope_key,
                     legacy_four_point_comparison_key=config['common_key'],
                     case_registry_sha256=sha(OUT / 'case_registry_candidate.json'),
                     new_case_ids=[r['id'] for r in rows if not r['existing_case_id']],
                     reused_case_aliases={r['id']:r['existing_case_id'] for r in rows if r['existing_case_id']},
                     cumulative_before=258, cumulative_if_all_21_attempted=279,
                     limits=dict(dynamic_episodes=21, environment_creations=21, resets=21,
                                 control_cycles=304500, native_steps=3045000,
                                 per_episode_cycles=14500, per_episode_native_steps=145000,
                                 per_episode_wall_s=1200, whole_wall_s=21600,
                                 policy_calls=0, learner_constructions=0, tensor_loads=0,
                                 formal_updates=0, replay_publications=0, independent_tests=0),
                     initial_checks_within_each_attempt=['registered_actual_xyz_and_quaternion',
                         'all_contacts_wrench_penetration_and_guard_audit', 'same_model_and_controller'],
                     zero_residual=[0.,0.,0.,0.], retries=0, old_budget_closed=True,
                     ordinary_valid_stopped_task_failure='retain_and_continue_within_fixed_case_order',
                     guard_invalid_unstopped_runtime_fault_source_drift='close_unspent_cases_no_retry',
                     whole_deadline='close_any_unspent_cases_report_incomplete_25_point_matrix',
                     prior_success_linear_planning_estimate_s=costs['package_wall_s']/4*21,
                     estimate_basis=dict(previous_wall_s=costs['package_wall_s'], previous_episodes=4,
                                         assumption='same_average_cost_only_not_measurement_or_guarantee'),
                     nonzero_SAC_scope_qualification_inherited=False,
                     deferred_frozen_actors=dict(F0_new_cells=21,F2000_new_cells=21,
                         admitted=False, reason='requires_actor_specific_runtime_scope_and_separate_finite_package'),
                     post_package='prepare_same_version_frozen_SAC_scope_and_compare_development_strata',
                     B2_complete=False, C_started=False, before_C_summary_required=True)
    write('execution_candidate.json', candidate)
    write('route_decision.json', dict(status='OFFLINE_PREPARATION_COMPLETE_EXECUTION_PENDING',
          next='implement_separate_21_case_zero_B2_entry_and_verify_offline',
          rationale='obtain_new_init_dynamic_and_traditional_baseline_data_in_one_attempt_per_case',
          no_separate_21_reset_only_physics_package=True, no_control_reward_or_threshold_change=True,
          main_method_requires_RL=True, full_B2_accepted=False, C_accepted=False,
          current_new_physical_episodes=0,current_new_model_constructions=0,current_new_policy_calls=0,
          current_new_tensors=0,current_new_updates=0,current_new_replay_publications=0,
          cumulative_dynamic=258,independent_tests=0,automatic_tracking='PAUSED'))
    write('analysis_receipt.json', dict(status='PASS_OFFLINE_SCREEN_LIMITED',
          analysed_at=datetime.now(timezone(timedelta(hours=8))).isoformat(), stdlib_only=True,
          inherited_inputs_verified=len(source['files']), prior_sealed_members_verified=77,
          prohibited_imports_loaded=[n for n in sys.modules if n.split('.')[0] in
              {'numpy','mujoco','torch','gymnasium','stable_baselines3'}], summary=result['summary']))
    print(json.dumps(result['summary'], ensure_ascii=False))


if __name__ == '__main__':
    main()
