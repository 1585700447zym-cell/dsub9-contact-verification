from copy import deepcopy
import math
import numpy as np
import pytest


@pytest.fixture
def residual(runtime):
    from tools.learning.guarded_environment import GuardCandidateConfig, LearningEnvironment
    from tools.learning.residual_session import ResidualSession
    from tools.validation.run_b1_baseline import cases
    env = LearningEnvironment(guard_config=GuardCandidateConfig(
        max_rotation_from_start_rad=math.radians(2.5), initial_roll_pitch_limit_rad=math.radians(1.5)))
    s = ResidualSession(environment=env)
    s.reset(cases()[0], seed=2026092201)
    return s


def test_nonzero_action_reaches_bounded_drive_and_real_motion(residual):
    s = residual
    initial = deepcopy(s.env.observe())
    for _ in range(20):
        result = s.advance_cycle([1, -1, 1, -1])
    assert result.next_snapshot.policy_observation
    assert s.env.data.qpos[0] > initial['position_m'][0]
    assert s.env.data.qpos[1] < initial['position_m'][1]
    assert s.env.data.qvel[3] > 0 and s.env.data.qvel[4] < 0
    assert s.last_action_log['experience_action'] == [1, -1, 1, -1]
    np.testing.assert_allclose(s.last_action_log['applied_residual'], [.00015, -.00015, 0, .005, -.005, 0])
    assert max(abs(np.array(result.executed_command)[:2])) <= .0005
    assert result.dt == pytest.approx(.002)
    assert result.reward_terms['time'] == pytest.approx(-.0002)
    assert result.outcome['training_admitted'] is False


def test_observe_prepare_do_not_advance_baseline_history_or_reward(residual):
    s = residual
    a = s.advance_cycle([.2, 0, 0, 0]).next_snapshot
    before = (s.controller_state_snapshot(), deepcopy(s.policy_raw), s.reward.maximum, s.env.physical_steps)
    for _ in range(4):
        assert s.prepare_cycle().policy_observation == a.policy_observation
        assert s.observe().policy_observation == a.policy_observation
    after = (s.controller_state_snapshot(), s.policy_raw, s.reward.maximum, s.env.physical_steps)
    assert before == after


def test_stopping_masks_valid_actions_but_not_invalid_actions(residual):
    s = residual
    s._finish('TIME_LIMIT')
    s._cache = None
    result = s.advance_cycle([1]*4)
    assert s.last_action_log['experience_action'] == [0]*4
    assert s.last_action_log['applied_residual'] == [0]*6
    assert result.next_snapshot.residual_enabled is False
    with pytest.raises(ValueError):
        s.advance_cycle([float('nan')]*4)
    assert not s.env.guard_facts['simulation_valid'] and s.done


def test_zero_residual_matches_same_guard_version_for_every_short_cycle(residual):
    from tools.learning.guarded_environment import LearningEnvironment
    from tools.learning.guarded_session import CandidateEpisodeSession
    from tools.validation.run_b1_baseline import cases
    base = CandidateEpisodeSession(environment=LearningEnvironment(guard_config=residual.env.guard_config))
    base.reset(cases()[0])
    for _ in range(20):
        expected = base.advance_cycle([0]*4)
        actual = residual.advance_cycle([0]*4)
        assert actual.trace_row == expected.trace_row
        assert actual.events == expected.events
        assert actual.executed_command == expected.executed_command
        assert actual.outcome == expected.outcome


def test_reset_clears_policy_history_previous_actions_and_reward(residual):
    from tools.validation.run_b1_baseline import cases
    expected = residual.observe().policy_observation
    residual.advance_cycle([1]*4)
    reset = residual.reset(cases()[0])
    assert reset.policy_observation == expected
    assert residual.reward.maximum == 0.
    assert residual.previous_residual == [0]*4


def test_full_stop_gives_one_terminal_reward_including_tail_time(residual):
    s = residual
    s._finish('TIME_LIMIT')
    s.task_finished = True
    s._cache = None
    total = 0.
    terminal_rewards = []
    while not s.done:
        result = s.advance_cycle([0]*4)
        total += result.reward_terms['total']
        terminal_rewards.append(result.reward_terms['terminal'])
    assert total == pytest.approx(-2.2, abs=1e-9)
    assert sum(x != 0 for x in terminal_rewards) == 1
    assert result.outcome['physical_stopped'] is True
    with pytest.raises(RuntimeError):
        s.advance_cycle([0]*4)


def test_invalid_target_reset_cannot_reuse_old_session(residual):
    from dataclasses import replace
    with pytest.raises(ValueError):
        residual.reset(replace(residual.case, target_depth_m=0.))
    with pytest.raises(RuntimeError):
        residual.observe()
    with pytest.raises(RuntimeError):
        residual.advance_cycle([0]*4)


def test_failed_observation_reset_closes_session_even_after_factory_recovers(residual):
    from tools.control.search_recovery import SearchRecovery
    def bad():
        c = SearchRecovery()
        c.theta = float('nan')
        return c
    residual.controller_factory = bad
    with pytest.raises(ValueError):
        residual.reset(residual.case)
    residual.controller.theta = 0.
    with pytest.raises(RuntimeError):
        residual.observe()
    with pytest.raises(RuntimeError):
        residual.advance_cycle([1]*4)
    assert not residual.env.guard_facts['simulation_valid']
    assert residual.interface_fault['controller']['theta'] == {'nonfinite': 'nan'}


def test_direct_advance_exception_cannot_resume(residual, monkeypatch):
    def broken_step(_):
        raise RuntimeError('engine adapter failure')
    with monkeypatch.context() as patch:
        patch.setattr(residual.env, 'step', broken_step)
        with pytest.raises(RuntimeError, match='engine adapter failure'):
            residual.advance_cycle([1]*4)
    assert residual.done and not residual.env.guard_facts['simulation_valid']
    with pytest.raises(RuntimeError):
        residual.advance_cycle([1]*4)


def test_stop_transition_observes_live_reference_without_changing_frozen_trace(residual):
    from dataclasses import replace
    from tools.control.search_recovery import SearchRecovery, SearchConfig
    s = residual
    s.controller_factory = lambda: SearchRecovery(replace(SearchConfig(), total_action_time_s=.004))
    s.reset(s.case)
    s.advance_cycle([1, 0, 0, 0])
    result = s.advance_cycle([1, 0, 0, 0])
    assert s.env.phase == 'STOPPING'
    assert result.trace_row['reference_qpos'] != s.env.reference.tolist()
    np.testing.assert_array_equal(s.policy_raw['reference_position_error_m'], [0., 0., 0.])
    assert s.observe().policy_raw['previous_limited_command'] == result.executed_command
