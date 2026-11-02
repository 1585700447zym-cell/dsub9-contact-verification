"""Regression checks for premature exit after recovery, independent of geometry."""
import ast
import importlib
import inspect
import textwrap

import numpy as np
import pytest

from tools.control.search_recovery import Observation, SearchRecovery


def api():
    return importlib.import_module('tools.control.search_exit_v2')


def obs(t, z, force=0., shift=0.):
    return Observation(t, (0., 0., z + shift), (0., 0., force, 0., 0., 0.))


def recovered(cls=None, shift=0.):
    c = (cls or api().SearchRecoveryV2)()
    for i in range(302):
        c.command(obs(i * .002, .00025, -.02, shift), .002)
    assert c.phase == 'UNLOAD'
    c.command(obs(.606, .00005, shift=shift), .002)
    c.command(obs(9., .00005, shift=shift), .002)
    assert c.phase == 'WAIT_RECOVERY'
    c.start_recovered_search(obs(10., -.00003, shift=shift))
    return c


def test_old_false_exit_is_blocked():
    old, new = recovered(SearchRecovery), recovered()
    old.command(obs(10.3, .000071), .002)
    new.command(obs(10.3, .000071), .002)
    assert old.phase == 'INSERT'
    assert new.phase == 'SEARCH'
    assert new.blocked_z_m == pytest.approx(.00025)


def test_crossing_old_depth_alone_is_insufficient_but_sustained_low_load_exits():
    c = recovered()
    c.command(obs(10.4, .00036), .002)
    assert c.phase == 'SEARCH'
    for i in range(1, 26):
        c.command(obs(10.4 + i * .002, .00036 + i * .4e-6, -.006), .002)
    assert c.phase == 'INSERT'
    event = c.events[-1]
    assert event['reason'] == 'SEARCH_ADVANCED'
    assert event['exit_evidence']['duration_s'] >= .05 - 1e-9
    assert event['exit_evidence']['advance_m'] >= 5e-6


@pytest.mark.parametrize('interruption', ['high_load', 'backtrack', 'sample_gap'])
def test_qualification_restarts_after_interruption(interruption):
    c = recovered()
    for i in range(20):
        c.command(obs(10.4 + i * .002, .00036 + i * .4e-6), .002)
    if interruption == 'high_load':
        c.command(obs(10.440, .00037, -.011), .002)
    elif interruption == 'backtrack':
        c.command(obs(10.440, .000369 - 2e-6), .002)
    # A missing interval must not be counted as continuously observed progress.
    restart = 10.5 if interruption == 'sample_gap' else 10.442
    for i in range(20):
        c.command(obs(restart + i * .002, .00037 + i * .4e-6), .002)
    assert c.phase == 'SEARCH'


def test_stationary_low_load_does_not_qualify_and_budget_is_preserved():
    c = recovered()
    for i in range(100):
        c.command(obs(10.4 + i * .002, .00036), .002)
    assert c.phase == 'SEARCH'
    c.command(obs(18.001, .00036), .002)
    assert c.phase == 'FAILED' and c.reason == 'SEARCH_BUDGET_EXHAUSTED'
    with pytest.raises(RuntimeError):
        c.start_recovered_search(obs(19., 0.))


def test_first_search_and_command_algorithm_are_unchanged_except_gate():
    old, new = SearchRecovery(), api().SearchRecoveryV2()
    for i in range(302):
        o = obs(i * .002, .00025, -.02)
        np.testing.assert_array_equal(old.command(o, .002), new.command(o, .002))
    for i in range(100):
        o = obs(.606 + i * .002, .00005 + i * 2e-6, -.004)
        np.testing.assert_array_equal(old.command(o, .002), new.command(o, .002))
        assert old.phase == new.phase
    source = inspect.getsource(SearchRecovery.command).replace(
        'delta[2]>=c.search_exit_advance_m', 'self._search_can_exit(obs,dt)')
    assert ast.dump(ast.parse(textwrap.dedent(source))) == ast.dump(
        ast.parse(textwrap.dedent(inspect.getsource(api().SearchRecoveryV2.command))))


def test_gate_uses_relative_history_not_target_pose():
    a, b = recovered(), recovered(shift=.01)
    for i in range(27):
        z = .00036 + i * .4e-6
        np.testing.assert_allclose(a.command(obs(10.4 + i*.002, z), .002),
                                   b.command(obs(10.4 + i*.002, z, shift=.01), .002), atol=1e-14)
        assert a.phase == b.phase
    assert a.phase == 'INSERT'


@pytest.mark.parametrize('kwargs', [{'hold_s': 0}, {'min_progress_m': float('nan')}, {'max_force_N': .025}])
def test_invalid_exit_parameters_rejected(kwargs):
    with pytest.raises(ValueError):
        api().ExitGateConfig(**kwargs)
