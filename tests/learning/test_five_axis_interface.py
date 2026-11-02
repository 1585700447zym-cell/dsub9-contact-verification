"""Five-axis behavior checks; no dynamics construction or research reset."""
from copy import deepcopy
from importlib import import_module, util
from types import SimpleNamespace
import numpy as np
import pytest


def api(name):
    module = 'tools.learning.five_axis_' + name
    assert util.find_spec(module) is not None, 'Five-axis implementation is not present'
    return import_module(module)


def fixture(phase='SEARCH', active=True):
    from tools.control.yaw_admittance import make_yaw_controller
    from tools.learning.types import CycleSnapshot
    controller = make_yaw_controller()
    row = dict(time_s=.1, phase='RUNNING', position_m=[0., 0., -.005], quaternion_wxyz=[1., 0., 0., 0.],
        velocity_world=[0.] * 6, contact_wrench_M=[0., 0., -2., 0., 0., .01],
        reference_qpos=[0., 0., -.005, 1., 0., 0., 0.], limited_command_world=[0.] * 6)
    state = dict(phase=phase, reason=None, phase_start=0., theta=0., search_count=1,
        search_origin=[0., 0., 0.], history=[], admittance_velocity=[0.] * 4,
        admittance_offset=[0.] * 4, episode_peak_z_m=0., search_progress_origin_z_m=0.,
        rotation_risk_since_s=None, search_load_since_s=None, admittance_xy_rebase_count=0,
        reference_release_requested=False, yaw_admittance=dict(velocity_rad_s=.002, offset_rad=.01))
    snap = CycleSnapshot(0, .1, [0.] * 6, active, row, state)
    facts = dict(simulation_valid=True, contact_reasons=[], motion_reasons=[], invalid_reasons=[])
    context = dict(reason=None, recovery_state=None, recovery_count=0, hold_start=None,
        wait_start=None, actual_stop_start=None, previous_residual=[1e-5, 2e-5, 3e-4, 4e-4, 5e-4],
        guard_facts=facts, previous_filter_fraction=1.)
    profile = SimpleNamespace(force_guard_N=5., torque_guard_Nm=.1)
    return controller, snap, context, profile


def test_five_actions_map_to_xy_and_three_rotations_without_z():
    a = api('action')
    result = a.map_residual([1., -1., 1., -1., 1.], enabled=True)
    np.testing.assert_array_equal(result, [.00005, -.00005, 0., .0005, -.0005, .0005])
    np.testing.assert_array_equal(a.map_residual([1.] * 5, enabled=False), np.zeros(6))


@pytest.mark.parametrize('value', [[0.] * 4, [0.] * 6, [0., 0., 0., 0., np.nan], [0., 0., 0., 0., 1.1]])
def test_reject_old_or_invalid_action(value):
    with pytest.raises(ValueError):
        api('action').normalized_action(value)


def test_zero_residual_does_not_reduce_450_search_or_passive_yaw():
    a = api('action')
    base = [.00045, -.00042, .0001, .005, -.006, .015]
    total, log = a.compose_command(base, [0.] * 5, phase='SEARCH', enabled=True,
        previous_limited=base, dt=.002, reference_xy=[0., 0.], radius=.0004)
    np.testing.assert_array_equal(total, base)
    np.testing.assert_array_equal(log['effective_command_delta'], np.zeros(6))


def test_yaw_residual_sign_and_angular_cap():
    a = api('action')
    for sign in [-1., 1.]:
        base = [0., 0., .0001, 0., 0., 0.]
        total, log = a.compose_command(base, [0., 0., 0., 0., sign], phase='INSERT',
            enabled=True, previous_limited=base, dt=.002)
        assert total[5] == pytest.approx(sign * .0005)
        assert log['predicted_limited_command'][5] == pytest.approx(sign * .0005)
    base[5] = .02
    total, _ = a.compose_command(base, [0., 0., 0., 0., 1.], phase='SEARCH', enabled=True,
        previous_limited=base, dt=.002, reference_xy=[0., 0.], radius=.0004)
    assert total[5] == .02


@pytest.mark.parametrize('phase', ['UNLOAD', 'WAIT_RECOVERY', 'FAILED'])
def test_disabled_stages_cannot_leak_a_requested_yaw(phase):
    a = api('action')
    _, log = a.compose_command([0.] * 6, [1.] * 5, phase=phase, enabled=False,
        previous_limited=[0.] * 6, dt=.002)
    assert log['experience_action'] == [0.] * 5
    assert log['applied_residual'] == [0.] * 6
    with pytest.raises(ValueError):
        a.compose_command([0.] * 6, [1.] * 5, phase=phase, enabled=True,
            previous_limited=[0.] * 6, dt=.002)


def test_reference_filter_keeps_search_command_inside_shared_disk():
    a = api('action')
    _, log = a.compose_command([0.] * 6, [1., 0., 0., 0., 1.], phase='SEARCH', enabled=True,
        previous_limited=[0.] * 6, dt=.002, reference_xy=[.0004, 0.], radius=.0004)
    assert np.linalg.norm(log['predicted_reference_xy_m']) <= .0004 + 1e-12
    assert log['reference_filter_fraction'] < 1.


def test_observation_is_140_with_only_required_yaw_fields_and_n2_wrench():
    controller, snap, context, profile = fixture()
    m = api('observation')
    builder = m.FiveAxisObservation(snap.state, controller.config, profile)
    vector, raw = builder.capture(snap, context)
    assert vector.shape == (140,)
    np.testing.assert_allclose(vector[-3:], [5e-4 / .03, .002 / .03, .01 / .08])
    assert vector[2] == pytest.approx(-2. / 5.)
    assert vector[5] == pytest.approx(.01 / .1)
    assert raw['previous_residual'] == context['previous_residual'][:4]
    assert raw['previous_yaw_residual'] == [5e-4]
    assert api('contract').permission(vector)
    assert builder.schema[-1]['start'] + builder.schema[-1]['width'] == 140


def test_history_is_four_control_samples_and_refresh_does_not_advance_it():
    controller, snap, context, profile = fixture()
    b = api('observation').FiveAxisObservation(snap.state, controller.config, profile)
    b.capture(snap, context)
    snap.cycle_id = 1
    snap.state['contact_wrench_M'][0] = 1.
    v, _ = b.capture(snap, context)
    v2, _ = b.capture(snap, context, refresh=True)
    np.testing.assert_array_equal(v[:24], v2[:24])
    assert v[:24].reshape(4, 6)[:, 0].tolist() == pytest.approx([.2, 0., 0., 0.])


def test_observation_does_not_read_privileged_pin_or_absolute_target_data():
    controller, snap, context, profile = fixture()
    b = api('observation').FiveAxisObservation(snap.state, controller.config, profile)
    a, _ = b.capture(snap, context)
    snap.state.update(pin_truth=[999.] * 9, hole_error=[1., 2., 3.], diagnostic_contact_pins=[6, 7])
    other, _ = b.capture(snap, context, refresh=True)
    np.testing.assert_array_equal(a, other)


def test_permission_rejects_stale_activity_and_legacy_dimensions():
    controller, snap, context, profile = fixture()
    b = api('observation').FiveAxisObservation(snap.state, controller.config, profile)
    v, _ = b.capture(snap, context)
    c = api('contract')
    with pytest.raises(ValueError): c.permission(v[:137])
    v[76] = 0.
    with pytest.raises(ValueError): c.permission(v)


def test_config_is_fresh_five_dimensional_ordinary_sac():
    c = api('contract')
    config = c.learning_config()
    assert config['width'] == 140 and config['action_dim'] == 5
    assert config['learning']['target_entropy'] == -5.
    assert not config['learning']['exact_terminal_tail']
    assert config['learning']['critic_boundary_rows'] == 0
    bad = deepcopy(config); bad['action_dim'] = 4
    with pytest.raises(ValueError): c.validate_config(bad)
