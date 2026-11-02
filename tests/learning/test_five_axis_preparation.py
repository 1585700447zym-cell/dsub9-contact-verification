"""Preparation gates only; never construct a physical environment."""
import importlib
import importlib.util
from copy import deepcopy
import numpy as np
import pytest


def module():
    name = 'tools.learning.five_axis_preparation'
    assert importlib.util.find_spec(name) is not None, 'Training preparation gate missing'
    return importlib.import_module(name)


def test_preparation_scope_has_three_attempts_and_no_retry_or_training():
    scope = module().preparation_scope()
    assert scope['max_initializations'] == 3 and scope['retries'] == 0
    assert scope['case_ids'] == ['ZERO_P10', 'PULSE_P10', 'PULSE_M10']
    assert scope['formal_training_updates'] == 0 and scope['cumulative_before'] == 372


def test_training_schedule_is_bounded_development_only_and_uses_current_config():
    p = module().training_plan()
    assert p['config']['width'] == 140 and p['config']['action_dim'] == 5
    assert len(p['schedule']) == p['max_initializations'] == 12
    assert [s['stage'] for s in p['schedule']] == ['warmup'] * 4 + ['online'] * 4 + ['development'] * 4
    assert sum(s['updates_after'] for s in p['schedule']) == 2000
    assert all(s['data_use'] == 'development_only' for s in p['schedule'])
    assert p['final_test_episodes'] == p['retries'] == 0
    assert p['max_physical_substeps'] == 12 * 14500 * 10


def test_pulses_cover_all_five_axes_both_signs_and_settle_before_contact():
    m = module()
    for segment in range(10):
        wanted = np.zeros(5); wanted[segment // 2] = 1. if segment % 2 == 0 else -1.
        for cycle in (segment * 30, segment * 30 + 19):
            np.testing.assert_array_equal(m.qualification_action('PULSE_P10', cycle), wanted)
        np.testing.assert_array_equal(m.qualification_action('PULSE_M10', segment * 30 + 29), np.zeros(5))
    np.testing.assert_array_equal(m.qualification_action('ZERO_P10', 20), np.zeros(5))
    with pytest.raises(ValueError): m.qualification_action('unknown', 0)


def test_source_digest_change_refuses_execution(tmp_path):
    m = module(); path = tmp_path / 'module.py'; path.write_text('original')
    pins = {'module.py': m.sha(path)}
    m.verify_inputs(pins, root=tmp_path)
    path.write_text('changed')
    with pytest.raises(ValueError): m.verify_inputs(pins, root=tmp_path)


def test_zero_comparison_covers_physical_state_and_stage_transition_rows():
    m = module()
    row = dict(time_s=0., position_m=[0.] * 3, quaternion_wxyz=[1., 0., 0., 0.],
               velocity_world=[0.] * 6, contact_wrench_M=[0.] * 6, contact_wrench_G=[0.] * 6,
               limited_command_world=[0.] * 6, phase='RUNNING')
    old = [row, dict(row, time_s=.002, phase='STOPPING')]
    assert m.compare_zero_trace(deepcopy(old), old)['rows'] == 2
    altered = deepcopy(old); altered[1]['position_m'][0] = 1e-6
    with pytest.raises(ValueError): m.compare_zero_trace(altered, old)
    altered = deepcopy(old); altered[1]['phase'] = 'RUNNING'
    with pytest.raises(ValueError): m.compare_zero_trace(altered, old)


def test_real_data_replay_shape_and_terminal_masks_are_checked_without_publication():
    from tests.learning.test_five_axis_learning import rows
    data = rows()
    m = module()
    assert m.validate_transitions(data)['rows'] == len(data)
    data[-1]['next_action_active'] = True
    with pytest.raises(ValueError): m.validate_transitions(data)


def test_unfinished_or_invalid_episode_cannot_become_ready():
    m = module()
    with pytest.raises(ValueError): m.audit_episode({}, {'status': 'error'}, {})


def test_ready_check_cannot_accept_a_self_reported_boolean(tmp_path):
    m = module()
    (tmp_path / 'admission.json').write_text('{"ready": true}')
    with pytest.raises((ValueError, FileNotFoundError, KeyError)):
        m.check_ready(tmp_path)


def test_training_entry_is_separate_and_does_not_start_when_describing(capsys):
    name = 'tools.validation.run_five_axis_training'
    assert importlib.util.find_spec(name) is not None, 'Training launcher missing'
    assert importlib.import_module(name).main(['--describe']) == 0
    assert '"max_initializations": 12' in capsys.readouterr().out


@pytest.mark.parametrize('damage', ['nonfinite', 'missing', 'count', 'alpha', 'actor'])
def test_checkpoint_diagnostic_history_rejects_corruption_without_mutation(damage):
    from tools.learning.five_axis_training import FiveAxisTrainer
    from tools.learning.five_axis_contract import learning_config
    from tools.learning.sac_checkpoint import _same
    from tests.learning.test_five_axis_learning import rows, OUTCOME
    config = learning_config(); config['learning']['batch_size'] = 8
    trainer = FiveAxisTrainer(config)
    trainer.publish('synthetic-only', rows(), outcome=OUTCOME, training_admitted=True)
    trainer.update_from_replay(); before = trainer.state_dict(); broken = deepcopy(before)
    record = broken['history'][0]
    if damage == 'nonfinite': record['critic_loss'] = float('nan')
    elif damage == 'missing': del record['critic_loss']
    elif damage == 'count': record['active_rows'] = 9
    elif damage == 'alpha': record['alpha_after'] = 0.
    else: record['actor_loss'] = None
    with pytest.raises(ValueError): trainer.load_state_dict(broken)
    assert _same(before, trainer.state_dict())


def test_reward_audit_recomputes_n2_load_progress_and_unique_terminal():
    m = module()
    terms = dict(progress=.1, time=-.0002, force=-.000016, torque=-.000004, terminal=-2.)
    terms['total'] = sum(terms.values())
    raw = dict(case={'target_depth_m': .005}, trace=[{'position_m': [0., 0., -.005]},
        {'position_m': [0., 0., -.0049]}], cycle_peaks=[{'force_N': 1., 'torque_G_Nm': .01}],
        outcome={'task_outcome': 'TASK_FAILURE'}, transitions=[dict(dt=.002, reward_terms=terms,
            reward=terms['total'])])
    m.verify_rewards(raw, final_reason='TIME_LIMIT')
    raw['transitions'][0]['reward_terms']['force'] = 0.
    with pytest.raises(ValueError): m.verify_rewards(raw, final_reason='TIME_LIMIT')


def test_resume_refuses_partial_episode_or_different_run_identity(tmp_path):
    m = module()
    job = training = m.training_plan()['schedule'][0]
    ledger = dict(episodes=[], training_updates=0)
    latest = dict(next_schedule_index=0, registration_sha256='reg', admission_sha256='admit')
    assert m.validate_resume_boundary(tmp_path, ledger, latest, 'reg', 'admit') == 0
    (tmp_path / job['id']).mkdir()
    with pytest.raises(ValueError): m.validate_resume_boundary(tmp_path, ledger, latest, 'reg', 'admit')
    with pytest.raises(ValueError): m.validate_resume_boundary(tmp_path, ledger, latest, 'wrong', 'admit')


def test_success_hold_uses_current_nine_pin_referee_at_90um():
    from tools.model.clearance_task import finish_criteria
    m = module(); criteria = dict(finish_criteria(), force_N=5., torque_Nm=.1)
    row = dict(position_m=[90e-6, 0., 0.], quaternion_wxyz=[1., 0., 0., 0.],
               velocity_world=[0.] * 6, contact_wrench_G=[0.] * 6, penetration_m=0.)
    trace = [dict(row, time_s=i * .002) for i in range(51)]
    m.verify_success_hold(trace, task_end_time_s=.1, period=.002, criteria=criteria)
    trace[-5]['position_m'] = [.001, 0., 0.]
    with pytest.raises(ValueError): m.verify_success_hold(trace, task_end_time_s=.1, period=.002, criteria=criteria)


def test_mutable_plan_can_change_without_invalidating_frozen_code(tmp_path):
    m = module(); code = tmp_path / 'code.py'; plan = tmp_path / 'plan.md'
    code.write_text('original code'); plan.write_text('unchecked tasks')
    pins = m.freeze_sources([code], snapshot_only=[plan], folder=tmp_path / 'snapshot', root=tmp_path)
    plan.write_text('completed tasks')
    m.verify_inputs(pins, root=tmp_path)
    assert (tmp_path / 'snapshot/plan.md').read_text() == 'unchecked tasks'
    code.write_text('changed code')
    with pytest.raises(ValueError): m.verify_inputs(pins, root=tmp_path)


def action_row(action, active=True):
    from tests.learning.test_five_axis_interface import fixture
    from tools.learning.five_axis_observation import FiveAxisObservation
    from tools.learning.five_axis_action import compose_command
    controller, snap, context, profile = fixture('INSERT' if active else 'UNLOAD', active)
    snap.base_command = [0.] * 6; snap.state['limited_command_world'] = [0.] * 6
    observation = FiveAxisObservation(snap.state, controller.config, profile).capture(snap, context)[0]
    _, log = compose_command(snap.base_command, action, phase='INSERT' if active else 'UNLOAD',
        enabled=active, previous_limited=[0.] * 6, dt=.002)
    log['actual_end_limited_command'] = log['predicted_limited_command']
    return dict(observation=observation.tolist(), action=log['experience_action'], action_active=active,
                dt=.002, action_log=log)


def test_action_audit_rejects_same_direction_wrong_gain():
    m = module(); row = action_row([0., 0., 0., 0., 1.])
    m.verify_action_mapping(row)
    row['action_log']['requested_residual'][5] *= .5
    with pytest.raises(ValueError): m.verify_action_mapping(row)


def test_command_audit_has_exact_inputs_and_rejects_a_different_previous_command():
    row = action_row([1., 0., 0., 0., 0.])
    assert row['action_log']['composition_inputs']['previous_limited_command'] == [0.] * 6
    row['action_log']['composition_inputs']['previous_limited_command'][0] = .0001
    with pytest.raises(ValueError): module().verify_action_mapping(row)


@pytest.mark.parametrize('damage', ['schedule', 'tail', 'cutoff'])
def test_pulse_audit_covers_zero_segments_tail_and_exact_cutoff(damage):
    m = module(); rows = [action_row(m.qualification_action('PULSE_P10', i)) for i in range(300)]
    rows += [action_row([0.] * 5, False)] * 1000
    raw = dict(transitions=rows, evidence=dict(stop_time_s=.6, task_end_time_s=.6))
    receipt = dict(case_id='PULSE_P10', final_reason='EXTERNAL_TRUNCATION')
    m.verify_pulse_schedule(raw, receipt)
    if damage == 'schedule': rows[25] = action_row([.1, 0., 0., 0., 0.])
    elif damage == 'tail': rows[350] = action_row([0., 0., 0., 0., .1])
    else: raw['evidence']['stop_time_s'] = .602
    with pytest.raises(ValueError): m.verify_pulse_schedule(raw, receipt)


@pytest.mark.parametrize('response', ['retract', 'native_stop'])
def test_command_audit_respects_autonomous_retraction_and_native_stop(response):
    from tools.learning.five_axis_contract import field_slices
    row = action_row([1., 0., 0., 0., 0.] if response == 'native_stop' else [0.] * 5,
                     response == 'native_stop')
    span = field_slices()['physical_phase']
    row['next_observation'] = row['observation'].copy()
    if response == 'retract':
        row['observation'][span] = [0., 0., 1., 0.]
        row['next_observation'][span] = [0., 0., 1., 0.]
        row['action_log']['actual_end_limited_command'] = [0., 0., -.00001, 0., 0., 0.]
    else:
        row['next_observation'][span] = [0., 1., 0., 0.]
        row['action_log']['actual_end_limited_command'] = [0.] * 6
    module().verify_action_mapping(row)
