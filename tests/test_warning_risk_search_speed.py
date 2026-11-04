"""Pure controller/command fixtures; no environment, model or neural calls."""
from copy import deepcopy
import math

import numpy as np
import pytest

from tools.control.risk_search import PoseObservation, RiskSearchRecovery
from tools.learning import global_residual_action as action_api


class CountingAdmittance:
    def __init__(self):
        self.calls = 0
        self.offset = np.zeros(4)
        self.velocity = np.zeros(4)

    def command(self, wrench, dt):
        self.calls += 1
        return np.array([0., 0., .001, .002, -.003, 0.])


def sample(time_s, *, angle=math.radians(1.6), fz=-.02, advancing=True):
    return PoseObservation(time_s, (0., 0., time_s*.001 if advancing else 0.),
                           (0., 0., fz, 0., 0., 0.), angle)


def controller(*, warning_only=False, searches=0):
    result = RiskSearchRecovery()
    result.warning_only = warning_only
    result.search_count = searches
    result.admittance = CountingAdmittance()
    return result


def test_warning_preserves_insert_timer_and_calls_parent_once_per_input():
    c = controller(warning_only=True, searches=2)
    c.phase_start = .3
    for now in (1., 1.048, 1.05, 1.1, 1.3):
        command = c.command(sample(now), .002)
        np.testing.assert_array_equal(command, [0., 0., .001, .002, -.003, 0.])
    assert c.phase == 'INSERT' and c.reason is None and c.phase_start == .3
    assert c.risk_since == 1.
    assert c.admittance.calls == 5
    assert len(c.events) == 1
    event = c.events[0]
    assert event['reason'] == 'LOADED_ROTATION_WARNING' and event['phase'] == 'INSERT'
    assert event['time_s'] == 1.05 and event['risk_since_s'] == 1.
    assert event['relative_rotation_rad'] == math.radians(1.6)
    assert event['axial_force_N'] == -.02


def test_warning_rearms_only_after_the_risk_condition_clears():
    c = controller(warning_only=True)
    for now in (1., 1.05, 1.2):
        c.command(sample(now), .002)
    c.command(sample(1.202, angle=0.), .002)
    assert c.risk_since is None
    c.command(sample(1.204), .002)
    c.command(sample(1.252), .002)
    assert len(c.events) == 1 and c.risk_since == 1.204
    c.command(sample(1.254), .002)
    assert len(c.events) == 2
    assert [e['risk_since_s'] for e in c.events] == [1., 1.204]
    assert c.admittance.calls == 7


def test_warning_does_not_suppress_ordinary_axial_stall():
    c = controller(warning_only=True)
    c.command(sample(1., advancing=False), .002)
    c.command(sample(1.05, advancing=False), .002)
    c.command(sample(1.4, advancing=False), .002)
    assert c.phase == 'UNLOAD'
    assert [e['reason'] for e in c.events] == ['LOADED_ROTATION_WARNING', 'AXIAL_STALL']
    assert c.admittance.calls == 3


@pytest.mark.parametrize('searches,phase,reason', [
    (0, 'UNLOAD', 'LOADED_ROTATION_RISK'),
    (2, 'FAILED', 'SEARCH_BUDGET_EXHAUSTED'),
])
def test_default_risk_unload_and_budget_failure_are_preserved(searches, phase, reason):
    c = RiskSearchRecovery()
    c.search_count = searches
    c.admittance = CountingAdmittance()
    c.command(sample(1.), .002)
    c.command(sample(1.05), .002)
    assert c.phase == phase and c.events[-1]['reason'] == reason
    assert not any(e['reason'] == 'LOADED_ROTATION_WARNING' for e in c.events)


def test_invalid_warning_input_cannot_mutate_the_timer_or_warning_state():
    c = controller(warning_only=True)
    c.command(sample(1.), .002)
    with pytest.raises(ValueError):
        c.command(sample(1.05, fz=float('nan')), .002)
    assert c.risk_since == 1. and c.phase == 'INSERT' and not c.events
    assert c.admittance.calls == 1


def test_original_risk_branch_honors_the_search_budget_hook():
    c = controller(searches=2)
    c.search_count_exhausted = lambda: False
    c.command(sample(1.), .002)
    c.command(sample(1.05), .002)
    assert c.phase == 'UNLOAD'
    assert c.events[-1]['reason'] == 'LOADED_ROTATION_RISK'


def compose(*, limit=None, phase='SEARCH'):
    parameters = dict(profile='G1', phase=phase, enabled=True,
        previous_limited=[.0008, -.0008, 0., 0., 0., 0.], dt=.002,
        reference_xy=[0., 0.])
    if limit is not None:
        parameters['search_xy_limit_m_s'] = limit
    return action_api.compose_command([.001, -.001, .001, 0., 0., 0.], [0.]*5,
                                      **parameters)


def test_search_limit_is_explicit_900_while_drive_slew_and_insert_stay_original():
    old_command, old_log = compose()
    new_command, new_log = compose(limit=.0009)
    np.testing.assert_array_equal(old_command[:2], [.00045, -.00045])
    np.testing.assert_array_equal(new_command[:2], [.0009, -.0009])
    np.testing.assert_allclose(new_log['predicted_limited_command'][:2], [.00081, -.00081], atol=1e-15)
    assert new_command[2] == old_command[2] == .001
    insert_command, _ = compose(limit=.0009, phase='INSERT')
    np.testing.assert_array_equal(insert_command[:2], [.0005, -.0005])
    assert new_log['search_xy_limit_m_s'] == .0009
    assert old_log.get('search_xy_limit_m_s', .00045) == .00045


def test_900_audit_recomposition_is_bound_to_the_registered_limit():
    command, log = compose(limit=.0009)
    replay = getattr(action_api, 'recompose_logged_command', None)
    assert callable(replay), 'A pure registered-limit recomposition entry is required'
    rebuilt, expected = replay(log, search_xy_limit_m_s=.0009)
    np.testing.assert_array_equal(rebuilt, command)
    assert expected == log
    with pytest.raises(ValueError, match='limit'):
        replay(log, search_xy_limit_m_s=.00045)
    modified = deepcopy(log)
    modified['search_xy_limit_m_s'] = .00045
    with pytest.raises(ValueError, match='limit'):
        replay(modified, search_xy_limit_m_s=.0009)


def test_old_450_log_without_an_explicit_limit_remains_recomposable():
    command, log = compose()
    log.pop('search_xy_limit_m_s', None)
    replay = getattr(action_api, 'recompose_logged_command', None)
    assert callable(replay), 'A pure registered-limit recomposition entry is required'
    rebuilt, expected = replay(log, search_xy_limit_m_s=.00045)
    np.testing.assert_array_equal(rebuilt, command)
    assert expected['stage_limited_total'] == log['stage_limited_total']


@pytest.mark.parametrize('limit', [True, 0., -.0009, float('inf'), float('nan'), .001001])
def test_invalid_search_limit_is_rejected_without_changing_drive_bounds(limit):
    with pytest.raises(ValueError, match='limit'):
        compose(limit=limit)
