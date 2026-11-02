import math
import numpy as np
import pytest


@pytest.fixture
def gym_env(runtime):
    from tools.learning.env import ResidualEnv
    from tools.learning.guarded_environment import GuardCandidateConfig, LearningEnvironment
    from tools.learning.residual_session import ResidualSession
    from tools.validation.run_b1_baseline import cases
    session = ResidualSession(environment=LearningEnvironment(guard_config=GuardCandidateConfig(
        max_rotation_from_start_rad=math.radians(2.5), initial_roll_pitch_limit_rad=math.radians(1.5))))
    return ResidualEnv(session=session, case=cases()[0])


def test_gym_step_exposes_only_whitelist_and_holds_experience(gym_env):
    e = gym_env
    obs, info = e.reset(seed=42)
    assert e.observation_space.contains(obs) and obs.dtype == np.float32
    assert info['training_admitted'] is False
    nxt, reward, terminated, truncated, info = e.step(np.array([1., 0, 0, 0]))
    assert e.observation_space.contains(nxt)
    assert not terminated and not truncated and e.sink == [] and e.attempts == []
    assert info['dt'] == pytest.approx(.002)
    assert info['discount'] == pytest.approx(.9998000199986667)
    assert reward == info['reward_terms']['total']
    assert info['action_log']['experience_action'] == [1, 0, 0, 0]
    assert len(info['action_log']['actual_end_limited_command']) == 6
    with pytest.raises(RuntimeError, match='active'):
        e.reset(seed=43)


def test_invalid_action_discards_earlier_experience_and_retains_attempt(gym_env):
    e = gym_env
    e.reset(seed=42)
    e.step([0]*4)
    with pytest.raises(ValueError):
        e.step([float('nan')]*4)
    assert e.sink == [] and len(e.attempts) == 1
    assert e.attempts[0]['outcome']['simulation_valid'] is False
    assert e.attempts[0]['publication']['committed'] == 0
    assert e.attempts[0]['fault']['action'][0] == {'nonfinite': 'nan'}
    assert len(e.attempts[0]['quarantined']) == 1
    with pytest.raises(RuntimeError):
        e.step([0]*4)
    e.reset(seed=43)
    assert len(e.attempts) == 1


def test_failed_initialization_is_recorded_without_resampling(gym_env):
    from dataclasses import replace
    e = gym_env
    bad = replace(e.case, roll_rad=math.radians(2))
    with pytest.raises(ValueError):
        e.reset(seed=123, options={'case': bad})
    assert len(e.attempts) == 1 and e.attempts[0]['seed'] == 123
    assert e.attempts[0]['outcome']['simulation_valid'] is False
    with pytest.raises(RuntimeError):
        e.step([0]*4)


def test_invalid_native_time_does_not_escape_quarantine(gym_env, monkeypatch):
    import mujoco
    e = gym_env
    e.reset(seed=42)
    e.step([0]*4)
    original = mujoco.mj_step
    def bad_step(model, data):
        original(model, data)
        data.time = float('nan')
    monkeypatch.setattr(mujoco, 'mj_step', bad_step)
    with pytest.raises(ValueError):
        e.step([0]*4)
    assert e.sink == [] and len(e.attempts) == 1
    assert e.attempts[0]['outcome']['simulation_valid'] is False
    assert e.attempts[0]['fault']['native_time_s'] == {'nonfinite': 'nan'}


def test_task_budget_is_termination_after_audit_not_truncation(gym_env):
    from dataclasses import replace
    from tools.control.search_recovery import SearchRecovery, SearchConfig
    e = gym_env
    e.session.controller_factory = lambda: SearchRecovery(replace(SearchConfig(), total_action_time_s=.004))
    e.reset(seed=42)
    terminal_count = 0
    for _ in range(1100):
        _, _, terminated, truncated, info = e.step([0]*4)
        assert not truncated
        terminal_count += info['reward_terms']['terminal'] != 0
        if terminated:
            break
    assert terminated and terminal_count == 1
    assert e.attempts[0]['outcome']['physical_stopped'] is True
    assert e.attempts[0]['publication']['committed'] == 0  # Candidate is never admitted.
    assert e.attempts[0]['quarantined'][-1]['terminated'] is True


def test_external_cut_preserves_cut_state_and_never_stages_tail(gym_env):
    e = gym_env
    e.reset(seed=42)
    e.step([1, 0, 0, 0])
    obs, reward, terminated, truncated, info = e.truncate_after_step([1, 0, 0, 0])
    assert truncated and not terminated
    attempt = e.attempts[0]
    rows = attempt['quarantined']
    assert len(rows) == 2 and rows[-1]['truncated'] and not rows[-1]['terminated']
    assert rows[-1]['next_observation'] == obs.tolist()
    assert rows[-1]['next_action_active'] is True
    assert rows[-1]['reward'] == reward and info['reward_terms']['terminal'] == 0
    assert info['cut_time_s'] == pytest.approx(.004)
    assert info['audit_end_time_s'] >= 2.004-1e-9
    assert attempt['outcome']['physical_stopped'] is True
    assert e.session.reward.finalized
    assert obs.tolist() != e.session.observe().policy_observation
    assert e.sink == []


def test_external_tail_invalidity_discards_entire_cut_episode(gym_env, monkeypatch):
    import mujoco
    e = gym_env
    e.reset(seed=42)
    original = mujoco.mj_step
    def fail_in_tail(model, data):
        if e.session.external_cut:
            raise RuntimeError('tail engine fault')
        original(model, data)
    monkeypatch.setattr(mujoco, 'mj_step', fail_in_tail)
    # Engine catches failures; the original cut still returns, audit denies it.
    _, _, terminated, truncated, info = e.truncate_after_step([0]*4)
    assert truncated and not terminated
    assert len(e.attempts[0]['quarantined']) == 1
    assert info['outcome']['simulation_valid'] is False and e.sink == []


@pytest.mark.parametrize('kwargs', [{'seed': -1}, {'options': {'case': None}}, {'options': []}])
def test_malformed_reset_arguments_are_counted_as_failed_attempts(gym_env, kwargs):
    with pytest.raises(Exception):  # Gym's invalid seed is gymnasium.error.Error.
        gym_env.reset(**kwargs)
    assert len(gym_env.attempts) == 1
    assert gym_env.attempts[0]['outcome']['simulation_valid'] is False
    assert gym_env.attempts[0]['publication'] == {'committed': 0, 'discarded': 0}
