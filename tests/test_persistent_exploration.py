"""Collection-noise persistence only: no environment, model or optimizer."""
from copy import deepcopy
import numpy as np
import pytest


def test_epsilon_refreshes_on_the_26th_active_cycle_and_not_before():
    from tools.learning.persistent_exploration import HeldExploration
    sampler = HeldExploration(71)
    expected = np.random.default_rng(71)
    first, second = expected.standard_normal(5), expected.standard_normal(5)
    for _ in range(25):
        np.testing.assert_array_equal(sampler.noise(phase='SEARCH', enabled=True), first)
    assert sampler.draw_count == 1 and sampler.active_calls == 25
    np.testing.assert_array_equal(sampler.noise(phase='SEARCH', enabled=True), second)
    assert sampler.draw_count == 2 and sampler.last_log['refreshed']


def test_held_epsilon_does_not_freeze_current_mean_and_standard_deviation():
    from tools.learning.persistent_exploration import HeldExploration
    sampler = HeldExploration(19)
    epsilon = np.random.default_rng(19).standard_normal(5)
    mean = np.zeros(5)
    log_std = np.zeros(5)
    first = sampler.action_from_parameters(mean, log_std, phase='INSERT', enabled=True)
    second = sampler.action_from_parameters(mean + .3, log_std - .4, phase='INSERT', enabled=True)
    np.testing.assert_allclose(first, np.tanh(epsilon), rtol=0, atol=1e-15)
    np.testing.assert_allclose(second, np.tanh(.3 + np.exp(-.4) * epsilon), rtol=0, atol=1e-15)
    assert sampler.draw_count == 1 and not np.array_equal(first, second)


def test_phase_permission_and_reset_clear_old_noise_without_stale_action():
    from tools.learning.persistent_exploration import HeldExploration
    sampler = HeldExploration(9)
    expected = np.random.default_rng(9)
    first, second, third = [expected.standard_normal(5) for _ in range(3)]
    np.testing.assert_array_equal(sampler.noise(phase='INSERT', enabled=True), first)
    np.testing.assert_array_equal(sampler.noise(phase='SEARCH', enabled=True), second)
    np.testing.assert_array_equal(sampler.noise(phase='WAIT_RECOVERY', enabled=False), np.zeros(5))
    assert sampler.remaining_cycles == 0
    np.testing.assert_array_equal(sampler.noise(phase='SEARCH', enabled=True), third)
    sampler.reset(seed=9)
    assert sampler.active_calls == sampler.draw_count == sampler.disabled_calls == 0
    np.testing.assert_array_equal(sampler.noise(phase='SEARCH', enabled=True), first)


def test_serialized_rng_and_hold_state_replay_exactly_without_shared_arrays():
    from tools.learning.persistent_exploration import HeldExploration
    original = HeldExploration(77)
    for _ in range(17):
        original.noise(phase='SEARCH', enabled=True)
    state = original.state_dict()
    restored = HeldExploration(1)
    restored.load_state_dict(state)
    saved_state = deepcopy(state)
    if state['cached_noise'] is not None:
        state['cached_noise'][0] = 12345.
    for index in range(60):
        phase, enabled = ('UNLOAD', False) if index == 12 else ('SEARCH', True)
        np.testing.assert_array_equal(original.noise(phase=phase, enabled=enabled),
                                      restored.noise(phase=phase, enabled=enabled))
        assert original.last_log == restored.last_log
    another = HeldExploration(2)
    another.load_state_dict(saved_state)
    assert another.active_calls == 17 and another.remaining_cycles == 8


def test_uniform_prewarm_actions_have_the_same_refresh_and_disable_rule():
    from tools.learning.persistent_exploration import HeldExploration
    sampler = HeldExploration(4, distribution='uniform')
    first = np.random.default_rng(4).uniform(-1., 1., 5)
    for _ in range(25):
        np.testing.assert_array_equal(sampler.noise(phase='SEARCH', enabled=True), first)
    assert np.all(abs(first) <= 1.) and sampler.draw_count == 1
    np.testing.assert_array_equal(sampler.noise(phase='STOPPING', enabled=False), np.zeros(5))
    assert sampler.remaining_cycles == 0 and sampler.disabled_calls == 1


def test_absolute_clock_noise_is_shared_despite_different_phase_and_disabled_history():
    from tools.learning.persistent_exploration import HeldExploration
    left, right = HeldExploration(31), HeldExploration(31)
    left.noise_at(0, phase='INSERT', enabled=True)
    right.noise_at(0, phase='SEARCH', enabled=True)
    np.testing.assert_array_equal(left.noise_at(1, phase='WAIT_RECOVERY', enabled=False), np.zeros(5))
    right.noise_at(1, phase='SEARCH', enabled=True)
    assert left.cached_noise is None
    np.testing.assert_array_equal(left.noise_at(2, phase='SEARCH', enabled=True),
                                  right.noise_at(2, phase='SEARCH', enabled=True))
    np.testing.assert_array_equal(left.noise_at(24, phase='INSERT', enabled=True),
                                  right.noise_at(24, phase='SEARCH', enabled=True))
    assert left.last_log['noise_slot'] == right.last_log['noise_slot'] == 0


def test_absolute_clock_boundary_order_and_restoration_are_explicit():
    from tools.learning.persistent_exploration import HeldExploration
    sampler = HeldExploration(44)
    first = sampler.noise_at(0, phase='SEARCH', enabled=True)
    np.testing.assert_array_equal(sampler.noise_at(24, phase='SEARCH', enabled=True), first)
    second = sampler.noise_at(25, phase='SEARCH', enabled=True)
    assert not np.array_equal(first, second) and sampler.last_log['noise_slot'] == 1
    with pytest.raises(ValueError, match='strictly increasing'):
        sampler.noise_at(25, phase='SEARCH', enabled=True)
    with pytest.raises(ValueError, match='strictly increasing'):
        sampler.noise_at(23, phase='SEARCH', enabled=True)
    restored = HeldExploration(1)
    restored.load_state_dict(sampler.state_dict())
    for cycle in (26, 49, 50):
        np.testing.assert_array_equal(sampler.noise_at(cycle, phase='SEARCH', enabled=True),
                                      restored.noise_at(cycle, phase='SEARCH', enabled=True))
        assert sampler.last_log == restored.last_log
