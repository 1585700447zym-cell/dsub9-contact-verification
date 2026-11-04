"""New common 30s protocol; all sessions use a test double, no physics/NN."""
from importlib import import_module
import numpy as np
import pytest


def api():
    return import_module('tools.learning.time_budget_trial')


def test_both_groups_share_the_new_protocol_and_only_speed_fields_differ():
    m = api(); a, b = [m.protocol_config(v) for v in (450, 900)]
    assert a['retry_policy'] == b['retry_policy'] == 'time_only'
    assert a['rotation_risk_policy'] == b['rotation_risk_policy'] == 'warning_only'
    assert a['passive_yaw_enabled'] is b['passive_yaw_enabled'] is True
    assert a['task_deadline_s'] == b['task_deadline_s'] == 30.
    assert a['optimizer_updates'] == b['optimizer_updates'] == 0
    ca, cb = a.pop('controller_config'), b.pop('controller_config')
    assert {k for k in ca if ca[k] != cb[k]} == {'spiral_speed_m_s', 'search_xy_component_speed_m_s'}
    assert a.pop('search_xy_limit_m_s') == .00045
    assert b.pop('search_xy_limit_m_s') == .0009
    a.pop('group'); b.pop('group')
    assert a == b


@pytest.mark.parametrize('speed', [0, True, 600, '900', float('nan')])
def test_only_the_two_requested_groups_are_registered(speed):
    with pytest.raises(ValueError): api().protocol_config(speed)


def test_new_controller_keeps_real_counts_and_legacy_remains_bounded():
    from tools.learning.global_residual_session import make_controller
    for speed in (450, 900):
        c = api().make_controller(search_speed_um_s=speed)
        c.search_count = 70
        assert not c.search_count_exhausted() and c.warning_only
        assert c.search_count == 70
        assert c.admittance.feedback_enabled
        assert c.drive_config.linear_speed_m_s == .001
        assert c.drive_config.linear_acceleration_m_s2 == .005
    old = make_controller(); old.search_count = 2
    assert old.search_count_exhausted() and not old.warning_only


def test_budget_observation_is_finite_honest_and_has_the_same_140_slots():
    from tests.learning.test_five_axis_interface import fixture
    from tools.learning.five_axis_contract import field_slices
    from tools.learning.newton_damping import NewtonProfile
    _, snap, context, _ = fixture()
    cfg = api().make_controller().config
    obs = api().TimeBudgetObservation(snap.state, cfg, NewtonProfile())
    snap.controller_state['search_count'] = 30; context['recovery_count'] = 29
    vector, raw = obs.capture(snap, context)
    assert len(vector) == 140 and np.isfinite(vector).all() and obs.slices == field_slices()
    for name in ('searches_remaining', 'recoveries_remaining'):
        assert raw[name] == [1.]
        assert vector[obs.slices[name]][0] == 1.
        field = next(f for f in obs.schema if f['name'] == name)
        assert field['source'] == 'time_only_retry_permission'
    assert obs.version == api().OBSERVATION_VERSION
    snap.time_s = 30.
    vector, raw = obs.capture(snap, context, refresh=True)
    assert raw['searches_remaining'] == raw['recoveries_remaining'] == [0.]


def session_fixture(speed=450):
    from tests.test_reference_consistency import session_fixture as old_fixture
    from tests.learning.test_five_axis_session import point
    old = old_fixture()
    old.env.retry_policy = 'time_only'
    old.env.recovery_count_exhausted = lambda: False
    s = api().session_class(speed)(old.env)
    s.reset(point())
    return s


@pytest.mark.parametrize('speed', [450, 900])
def test_session_exposes_the_group_limit_without_changing_drive_limits(speed):
    s = session_fixture(speed)
    s.controller.phase = 'SEARCH'; s.controller.search_count = 10
    s.controller.search_origin = np.zeros(3); s.controller.search_progress_origin_z_m = 0.
    s._cache = None
    s._command_for_action(s.prepare_cycle(), np.ones(5))
    assert s.contract == api().protocol_config(speed)
    assert s.observations.version == api().OBSERVATION_VERSION
    assert s.last_action_log['search_xy_limit_m_s'] == speed / 1e6
    assert s.env.config.linear_speed == .001 and s.env.config.linear_acceleration == .005
    assert s._rebase_permitted(9)


def test_reference_exhaustion_after_many_retries_requests_recovery():
    s = session_fixture(); s.controller.phase = 'SEARCH'; s.controller.search_count = 20
    s.env.reference_failure_pending = True; s.env.stop('B2_SEARCH_EXHAUSTED')
    s._post_task_cycle(s.env.observe())
    assert s.reason is None and s.controller.phase == 'WAIT_RECOVERY'
    assert s.recovery_state == 'WAIT_STOP'


@pytest.mark.parametrize('state', ['WAIT_STOP', 'RETRACT', 'WAIT_RESUME', None])
def test_absolute_30s_deadline_precedes_every_retry_stage(state):
    s = session_fixture(); s.recovery_state = state; s.wait_start = 29.9
    s.env.data.time = 30.; s._cache = None
    snap = s.prepare_cycle()
    assert s.reason == 'TIME_LIMIT' and not snap.residual_enabled
    assert s.stop_time == 30. and s.env.data.time == 30.


def test_collector_rejects_legacy_contract_before_any_reset():
    from types import SimpleNamespace
    s = SimpleNamespace(contract={'version': 'old'})
    with pytest.raises(ValueError, match='new time-budget'):
        api().collect_episode(s, None, policy=None)


def test_new_session_rejects_an_old_count_limited_environment():
    from tests.test_reference_consistency import session_fixture as old_fixture
    with pytest.raises(TypeError, match='time-only recovery'):
        api().session_class()(old_fixture().env)


def test_multiple_xy_rebases_keep_the_existing_release_and_reset_gates():
    s = session_fixture(); c = s.controller
    snap = s.prepare_cycle(); snap.residual_enabled = False
    snap.controller_state['phase'] = 'UNLOAD'; snap.base_command = [0.] * 6
    for count in (2, 3, 4):
        c.phase = 'UNLOAD'; c.search_count = count
        c.reference_release_requested = True
        c.admittance.offset[:] = [.0001, -.0001, .02, -.02]
        c.admittance.velocity[:] = [.0001, -.0001, .001, -.001]
        s._command_for_action(snap, np.zeros(5))
        assert not c.reference_release_requested
        np.testing.assert_array_equal(c.admittance.offset[:2], [0., 0.])
        assert c.admittance.offset[2] != 0.
    assert sum(e['reason'] == 'XY_ADMITTANCE_REBASED' for e in c.events) == 3


def test_new_group_audit_reconstructs_900_and_rejects_a_450_registration():
    s = session_fixture(900)
    s.controller.phase = 'SEARCH'; s.controller.search_count = 3
    s.controller.search_origin = np.zeros(3); s.controller.search_progress_origin_z_m = 0.
    s._cache = None; snap = s.prepare_cycle()
    s._command_for_action(snap, np.ones(5))
    assert api().verify_group_composition(s.last_action_log, snap.policy_observation, s.contract)
    with pytest.raises(ValueError):
        api().verify_group_composition(s.last_action_log, snap.policy_observation, api().protocol_config(450))


def test_group_audit_rejects_a_self_consistent_wrong_residual_profile():
    from tools.learning.global_residual_action import compose_command
    from tests.learning.test_five_axis_interface import fixture
    _, snap, context, profile = fixture()
    cfg = api().make_controller().config
    obs, _ = api().TimeBudgetObservation(snap.state, cfg, profile).capture(snap, context)
    _, log = compose_command([0.]*6, [1.]*5, profile='G0', phase='SEARCH', enabled=True,
        previous_limited=[0.]*6, dt=.002, reference_xy=[0., 0.], search_xy_limit_m_s=.0009)
    log['contract_version'] = api().VERSION
    with pytest.raises(ValueError, match='contract'):
        api().verify_group_composition(log, obs, api().protocol_config(900))
