"""Pure command and fake-environment lifecycle tests; no physical simulation."""
import importlib
from dataclasses import asdict
import numpy as np
import pytest


def api():
    return importlib.import_module('tools.learning.global_residual_action')


def test_profiles_map_five_axes_without_z_and_validate_inputs():
    m = api()
    np.testing.assert_array_equal(m.map_residual([1, -1, 1, -1, 1], profile='G1', enabled=True),
                                  [.0005, -.0005, 0., .0005, -.0005, .005])
    for profile in ('G0', 'G1'):
        np.testing.assert_array_equal(m.map_residual([1]*5, profile=profile, enabled=False), np.zeros(6))
    for action in ([0]*4, [0, 0, 0, 0, np.nan], [2]*5):
        with pytest.raises(ValueError):
            m.map_residual(action, profile='G1', enabled=True)
    with pytest.raises(ValueError):
        m.profile_config('OTHER')


def test_original_scale_and_zero_requests_match_original_algorithm():
    m = api()
    from tools.learning.five_axis_action import compose_command as old
    rng = np.random.default_rng(17)
    for phase in ('SEARCH', 'INSERT', 'UNLOAD'):
        for _ in range(24):
            args = dict(phase=phase, enabled=phase != 'UNLOAD', previous_limited=rng.uniform(-.0002,.0002,6),
                        dt=.002, reference_xy=[.0001, -.0001])
            base = rng.uniform(-.0002,.0002,6)
            action = rng.uniform(-1,1,5)
            a, al = old(base, action, **args)
            b, bl = m.compose_command(base, action, profile='G0', **args)
            np.testing.assert_array_equal(a,b)
            for key in al:
                assert al[key] == bl[key]
            z0, _ = m.compose_command(base,[0]*5,profile='G0',**args)
            z1, _ = m.compose_command(base,[0]*5,profile='G1',**args)
            np.testing.assert_array_equal(z0,z1)


def test_large_request_keeps_total_caps_and_can_reverse_baseline():
    m = api()
    common = dict(profile='G1',phase='SEARCH',enabled=True,dt=.002,
                  previous_limited=[.00045,0,0,0,0,.02],reference_xy=[0,0])
    total, log = m.compose_command([.00045,0,0,0,0,.02],[-1,0,0,0,1],**common)
    assert total[0] == pytest.approx(-.00005)
    assert total[5] == .02
    assert log['predicted_limited_command'][0] == pytest.approx(.00044)
    assert log['requested_residual'][0] == -.0005
    total, _ = m.compose_command([.00045,0,0,0,0,.02],[1,0,0,0,1],**common)
    assert total[0] == .00045


def test_disk_filter_still_couples_xy_and_yaw_and_disabled_phases_do_not_leak():
    m = api()
    _, log = m.compose_command([0]*6,[1,0,0,0,1],profile='G1',phase='SEARCH',enabled=True,
                               previous_limited=[0]*6,dt=.002,reference_xy=[.0004,0])
    assert log['reference_filter_fraction'] < 1e-8
    assert abs(log['predicted_limited_command'][5]) < 1e-8
    for phase in ('UNLOAD','WAIT_RECOVERY','FAILED'):
        _, log = m.compose_command([0]*6,[1]*5,profile='G1',phase=phase,enabled=False,
                                   previous_limited=[0]*6,dt=.002)
        assert log['applied_residual'] == [0]*6
        with pytest.raises(ValueError):
            m.compose_command([0]*6,[1]*5,profile='G1',phase=phase,enabled=True,
                              previous_limited=[0]*6,dt=.002)


def test_controller_and_session_keep_old_search_and_use_30s_observation():
    from tools.learning.global_residual_session import session_class, make_controller
    from tools.control.yaw_admittance import make_yaw_controller
    old, new = make_yaw_controller(), make_controller()
    old_cfg, new_cfg = asdict(old.config), asdict(new.config)
    old_cfg['total_action_time_s'] = 30.
    assert old_cfg == new_cfg
    from tests.learning.test_five_axis_session import fake_environment, point
    s = session_class('G1')(fake_environment())
    first = s.reset(point())
    assert len(first.policy_observation) == 140
    assert s.observations.version == 'five_axis_short_history_N2_30s_v1'
    r = s.advance_cycle([0,0,0,0,1])
    assert r.action_log['requested_residual'][5] == .005
    s.reset(point())
    assert s.previous_residual == [0]*5
    assert s.controller.admittance.yaw_offset == 0
    assert s.prepare_cycle().policy_observation[137] == 0


def test_deadline_permission_and_normalized_clock_use_30_not_25():
    from tools.learning.global_residual_session import session_class
    from tools.learning.five_axis_contract import field_slices
    from tests.learning.test_five_axis_session import fake_environment, point
    env = fake_environment()
    def stop(reason):
        env.phase = 'STOPPING'
        env.events.append(dict(time_s=env.data.time,reason=reason,phase=env.phase))
    env.stop = stop
    s = session_class('G0')(env); s.reset(point())
    env.data.time = 25.
    s.controller.phase_start = 25.
    s._cache = None
    snap = s.prepare_cycle()
    assert snap.residual_enabled and s.reason is None
    assert snap.policy_observation[field_slices()['total_budget_remaining_s']][0] == pytest.approx(5/30)
    env.data.time = 30.
    s._cache = None
    snap = s.prepare_cycle()
    assert not snap.residual_enabled and s.reason == 'TIME_LIMIT'
    assert s.stop_time == 30.
