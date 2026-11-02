"""Small saved-evidence checks; no environment, contact rollout or optimizer."""
from copy import deepcopy
from dataclasses import replace
import gzip
import hashlib
import importlib
from importlib.util import find_spec
import json
import math
import numpy as np
import pytest


def api():
    name = 'tools.validation.consistent_sac_audit'
    assert find_spec(name) is not None, 'Independent consistent-reference SAC audit is missing'
    return importlib.import_module(name)


def source_fixture(stage='online'):
    from tools.learning.five_axis_contract import learning_config
    from tools.learning.five_axis_training import FiveAxisTrainer
    from tests.learning.test_five_axis_learning import obs
    config = learning_config(); config['learning']['network'] = [8]
    source = FiveAxisTrainer(config)
    collector = FiveAxisTrainer(config); collector.load_state_dict(source.state_dict())
    observations = [obs(), obs(), obs(False)]
    rows = []
    for observation in observations:
        from tools.learning.five_axis_contract import permission
        active = permission(observation)
        action = collector.action(observation, deterministic=stage == 'development', warmup=stage == 'warmup')
        rows.append(dict(observation=observation.tolist(), action_active=active,
                         action_log=dict(raw_action=action.tolist())))
    raw = dict(transitions=rows, action_provider_calls=2, action_provider_successes=2,
               policy_calls=collector.policy_calls, warmup_draws=collector.warmup_draws)
    receipt = dict(policy_calls=collector.policy_calls, warmup_draws=collector.warmup_draws)
    return raw, receipt, dict(stage=stage), source


@pytest.mark.parametrize('stage', ['warmup', 'online', 'development'])
def test_saved_requests_are_reproduced_from_source_observations_and_rng(stage):
    raw, receipt, job, source = source_fixture(stage)
    proof = api().verify_action_source(raw, receipt, job, source_trainer=source)
    assert proof['verified'] and proof['active_rows'] == 2
    assert proof['policy_calls'] == (0 if stage == 'warmup' else 2)


def test_action_table_and_false_policy_call_counts_are_rejected():
    raw, receipt, job, source = source_fixture()
    raw['transitions'][0]['action_log']['raw_action'][0] += .01
    with pytest.raises(ValueError, match='source policy'):
        api().verify_action_source(raw, receipt, job, source_trainer=source)
    raw, receipt, job, source = source_fixture()
    receipt['policy_calls'] += 1
    with pytest.raises(ValueError, match='call'):
        api().verify_action_source(raw, receipt, job, source_trainer=source)


def test_neural_episode_requires_source_and_baseline_requires_zero_requests():
    raw, receipt, job, _ = source_fixture()
    with pytest.raises(ValueError, match='source trainer'):
        api().verify_action_source(raw, receipt, job)
    zero = deepcopy(raw)
    for row in zero['transitions']:
        row['action_log']['raw_action'] = [0.] * 5
    zero.update(policy_calls=0, warmup_draws=0)
    receipt = dict(policy_calls=0, warmup_draws=0)
    assert api().verify_action_source(zero, receipt, dict(stage='baseline'))['verified']
    zero['transitions'][0]['action_log']['raw_action'][4] = .1
    with pytest.raises(ValueError, match='baseline'):
        api().verify_action_source(zero, receipt, dict(stage='baseline'))


def reference_fixture():
    from tools.dynamics.reference_envelope import VERSION
    raw = dict(trace=[dict(phase='RUNNING', policy_phase='SEARCH',
        position_m=[.000278, .000160, -.005],
        reference_qpos=[.000390, .000030, -.005, 1., 0., 0., 0.],
        reference_center_xy_m=[0., 0.],
        reference_consistency=dict(version=VERSION, active=True))])
    # Use a jointly feasible point, with distinct actual and drive reference.
    raw['trace'][0]['position_m'][1] = .000140
    receipt = dict(physical_substeps=10, dynamic_config=dict(reference_lead_m=.00012),
        controller_config=dict(spiral_radius_m=.0004), reference_checks=dict(
            pre_pd_checks=10, post_step_checks=10, feasible_checks=20, infeasible_checks=0,
            max_disk_excess_m=0., max_lead_excess_m=0.))
    return raw, receipt


def test_real_reference_and_native_aggregate_must_satisfy_both_bounds():
    raw, receipt = reference_fixture()
    assert api().verify_reference_checks(raw, receipt)['verified']
    for change in ('disk', 'lead', 'missing_checks'):
        damaged, report = deepcopy(raw), deepcopy(receipt)
        if change == 'disk': damaged['trace'][0]['reference_qpos'][0] = .000401
        elif change == 'lead': damaged['trace'][0]['position_m'][0] = 0.
        else: report['reference_checks']['pre_pd_checks'] = 0
        with pytest.raises(ValueError):
            api().verify_reference_checks(damaged, report)


def test_projection_prediction_uses_current_actual_without_claiming_next_reference():
    from tools.learning.global_residual_action import compose_command
    from tools.dynamics.reference_envelope import VERSION, constrain_xy
    _, log = compose_command([0.] * 6, [0.] * 5, profile='G1', phase='SEARCH', enabled=True,
                             previous_limited=[0.] * 6, dt=.002, reference_xy=[-.000398, -.000030])
    actual, reference = [-.000278, -.000160], [-.000398, -.000030]
    log.update(reference_consistency_version=VERSION,
        contract_version='global_residual_G1_30s_reference_consistent_v1',
        reference_before_xy_m=reference, actual_before_xy_m=actual, reference_center_xy_m=[0., 0.],
        predicted_bounded_reference_xy_m=constrain_xy(reference, actual, [0., 0.], .0004, .00012).tolist(),
        bounded_prediction_infeasible=False, bounded_prediction_assumes_fixed_actual=True)
    state = dict(position_m=actual + [-.005])
    cfg = dict(spiral_radius_m=.0004)
    assert api().verify_reference_prediction(log, state, cfg, .00012)
    log['predicted_bounded_reference_xy_m'] = reference
    with pytest.raises(ValueError, match='prediction'):
        api().verify_reference_prediction(log, state, cfg, .00012)


def stopped_archive_fixture(folder):
    """Fabricated stopped evidence exercises the auditor, never a live engine."""
    from tests.learning.test_five_axis_interface import fixture
    from tools.learning.five_axis_observation import FiveAxisObservation
    from tools.learning.five_axis_preparation import cases
    from tools.learning.consistent_sac import VERSION, execution_contract
    from tools.learning.global_residual_action import compose_command
    from tools.dynamics.reference_envelope import VERSION as reference_version
    case = cases()[0]; contract = execution_contract()
    controller, snap, context, profile = fixture('UNLOAD', False)
    controller.config = replace(controller.config, total_action_time_s=30.)
    position = [case['x_offset_m'], case['y_offset_m'], case['start_origin_z_m']]
    # Independent elementary quaternion products avoid importing a native engine.
    def multiply(a, b):
        w, x, y, z = a; v, i, j, k = b
        return [w*v-x*i-y*j-z*k, w*i+x*v+y*k-z*j,
                w*j-x*k+y*v+z*i, w*k+x*j-y*i+z*v]
    rotation = [[math.cos(case[key]/2)] +
                [math.sin(case[key]/2) if axis == index else 0. for axis in range(3)]
                for index, key in enumerate(('roll_rad', 'pitch_rad', 'yaw_rad'))]
    quaternion = multiply(rotation[2], multiply(rotation[1], rotation[0]))
    context.update(reason='SEARCH_BUDGET_EXHAUSTED', previous_residual=[0.]*5, actual_stop_start=0.)
    trace, observations = [], []
    builder = None
    for index in range(1001):
        snap.cycle_id = index
        snap.time_s = index*.002
        snap.state.update(time_s=snap.time_s, phase='STOPPING', position_m=position,
            quaternion_wxyz=quaternion, contact_wrench_M=[0.]*6, contact_wrench_G=[0.]*6,
            reference_qpos=position+quaternion, limited_command_world=[0.]*6,
            reference_center_xy_m=None, reference_consistency=dict(version=reference_version, active=False))
        if builder is None:
            builder = FiveAxisObservation(snap.state, controller.config, profile)
            builder.version = contract['observation_version']
        observations.append(builder.capture(snap, context)[0].tolist())
        trace.append(deepcopy(snap.state))
    _, log = compose_command([0.]*6, [0.]*5, profile='G1', phase='UNLOAD', enabled=False,
                             previous_limited=[0.]*6, dt=.002)
    log.update(actual_end_limited_command=[0.]*6, contract_version=contract['version'],
               reference_consistency_version=reference_version)
    rows = []
    for index in range(1000):
        terms = dict(progress=0., time=-.0002, force=0., torque=0., terminal=-2. if index == 999 else 0.)
        terms['total'] = sum(terms.values())
        rows.append(dict(observation=observations[index], next_observation=observations[index+1],
            action=[0.]*5, action_active=False, next_action_active=False, action_log=deepcopy(log),
            dt=.002, discount=math.exp(-.002/10), terminated=index == 999, truncated=False,
            reward=terms['total'], reward_terms=terms))
    facts = dict(simulation_valid=True, invalid_reasons=[], motion_reasons=[], contact_reasons=[], checked_substeps=10000)
    raw = dict(version=contract['version'], learning_version=VERSION, execution_contract=contract,
        observation_version=contract['observation_version'], observation_schema=builder.schema,
        case=case, seed=5, transitions=rows, trace=trace, policy_calls=0, warmup_draws=0,
        action_provider_calls=0, action_provider_successes=0,
        cycle_peaks=[dict(force_N=0., torque_G_Nm=0.) for _ in rows],
        cost=dict(physical_substeps=10000, initialization_attempts=1, initializations_completed=1),
        outcome=dict(simulation_valid=True, physical_stopped=True, task_outcome='TASK_FAILURE'),
        evidence=dict(guard_facts=facts, interface_fault=None, diagnostic_errors={}, stop_time_s=0., task_end_time_s=0.,
            environment_events=[dict(time_s=0., phase='STOPPING')],
            stop_samples=[dict(time_s=i*.0002, linear_m_s=0., angular_rad_s=0.) for i in range(1, 10001)]))
    common = dict(dynamic_config=dict(control_period=.002, timestep=.0002, reference_lead_m=.00012),
                  effective_kd=[1.]*6, model_xml_sha256=hashlib.sha256(b'synthetic XML').hexdigest(), actual_model={}, runtime={})
    receipt = dict(common, status='finished', valid=True, stopped=True, nonfinite_fields=[],
        execution_contract=contract, case=case, seed=5, guard_facts=facts, control_cycles=1000,
        physical_substeps=10000, reset_attempted=1, policy_calls=0, warmup_draws=0,
        controller_config=dict(total_action_time_s=30., search_time_s=18., spiral_radius_m=.0004, settle_time_s=1.),
        final_reason='SEARCH_BUDGET_EXHAUSTED', outcome='TASK_FAILURE', reference_checks=dict(
            pre_pd_checks=0, post_step_checks=0, feasible_checks=0, infeasible_checks=0,
            max_disk_excess_m=0., max_lead_excess_m=0.))
    reg = dict(execution_contract=contract, common=common)
    job = dict(stage='baseline', case=case, seed=5)
    (folder/'model_used.xml').write_bytes(b'synthetic XML')
    def publish():
        encoded = gzip.compress(json.dumps(raw).encode('utf-8'), mtime=0)
        (folder/'episode.json.gz').write_bytes(encoded)
        receipt['archive_sha256'] = hashlib.sha256(encoded).hexdigest()
        (folder/'receipt.json').write_text(json.dumps(receipt), encoding='utf-8')
    publish()
    return raw, receipt, reg, job, publish


def test_complete_saved_archive_audit_and_initial_pose_binding(tmp_path):
    raw, receipt, reg, job, publish = stopped_archive_fixture(tmp_path)
    _, _, proof = api().audit_archive(tmp_path, reg, job)
    assert proof['verified'] and proof['stop']['final_native_samples'] == 10000
    raw['trace'][0]['quaternion_wxyz'] = [1., 0., 0., 0.]
    publish()
    with pytest.raises(ValueError, match='initial pose'):
        api().audit_archive(tmp_path, reg, job)
