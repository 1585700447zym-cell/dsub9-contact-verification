import math
import pytest


@pytest.fixture
def candidate_session(runtime):
    from tools.learning.guarded_environment import GuardCandidateConfig, LearningEnvironment
    from tools.learning.guarded_session import CandidateEpisodeSession
    from tools.validation.run_b1_baseline import cases
    env = LearningEnvironment(guard_config=GuardCandidateConfig(
        max_rotation_from_start_rad=math.radians(2.5), initial_roll_pitch_limit_rad=math.radians(1.5)))
    session = CandidateEpisodeSession(environment=env)
    session.reset(cases()[0])
    return session


def test_finite_motion_failure_reaches_session_without_old_invalid_label(candidate_session):
    s = candidate_session
    row = s.env.observe()
    row['velocity_world'][0] = .021
    s.env._guard(row)
    result = s.advance_cycle([0]*4)
    assert s.reason == 'MOTION_VIOLATION'
    assert s.guard_latched is True
    assert s.recovery_state is None
    assert result.next_snapshot.residual_enabled is False
    assert result.outcome['task_outcome'] == 'MOTION_VIOLATION'
    assert result.outcome['simulation_valid'] is True
    assert result.outcome['valid_for_learning'] is False


def test_contact_beats_motion_and_tail_fault_beats_previously_decided_success(candidate_session):
    s = candidate_session
    s._finish('GEOMETRIC_SUCCESS')
    s.task_finished = True
    row = s.env.observe()
    row['velocity_world'][0] = .021
    row['contact_wrench_M'][0] = .026
    s.env._guard(row)
    result = s.advance_cycle([0]*4)
    # Historical task decision remains historical; final adjudication sees tail faults.
    assert s.reason == 'GEOMETRIC_SUCCESS'
    assert result.outcome['task_outcome'] == 'CONTACT_GUARD'
    assert result.outcome['guard_violations'] == {'contact': True, 'motion': True}
    assert result.outcome['physical_stopped'] is False


def test_candidate_audit_requires_complete_tail_and_never_grants_training(candidate_session):
    s = candidate_session
    s._finish('TIME_LIMIT')
    s.task_finished = True
    while not s.done:
        result = s.advance_cycle([0]*4)
    assert result.outcome['physical_stopped'] is True
    assert result.outcome['simulation_valid'] is True
    assert result.outcome['task_outcome'] == 'TASK_FAILURE'
    assert result.outcome['model_scope_qualified'] is False
    assert result.outcome['valid_for_learning'] is False


@pytest.mark.parametrize('action', [[float('nan'), 0, 0, 0], [0, 0, 0], [2, 0, 0, 0]])
def test_invalid_action_latches_even_while_stopping(candidate_session, action):
    s = candidate_session
    s._finish('TIME_LIMIT')
    with pytest.raises(ValueError):
        s.advance_cycle(action)
    assert s.env.guard_facts['simulation_valid'] is False
    assert 'INVALID_COMMAND' in s.env.guard_facts['invalid_reasons']
    assert s.done is True
    assert s.observe().residual_enabled is False
    assert s.adjudicate()['task_outcome'] == 'INVALID_SIMULATION'


def test_candidate_guards_preserve_real_retraction_and_new_stop_segment(candidate_session):
    import numpy as np
    from tools.control.search_recovery import SearchConfig, SearchRecovery
    from tools.validation.run_b1_baseline import cases
    from tools.validation.native313_matrix_audit import actual_stop_start
    s = candidate_session
    def ready():
        c = SearchRecovery(SearchConfig(search_time_s=.002))
        c.phase = 'SEARCH'
        c.search_count = 1
        c.search_origin = np.zeros(3)
        c.phase_start = -.01
        return c
    s.controller_factory = ready
    s.reset(cases()[0])
    assert actual_stop_start(s.env.events, None) == 0.
    for _ in range(1000):
        result = s.advance_cycle([0]*4)
        if s.env.phase == 'RETRACT':
            assert result.next_snapshot.residual_enabled is False
        if s.controller.search_count == 2:
            break
    assert s.controller.search_count == 2 and s.env.phase == 'RUNNING'
    assert s.env.recovery_start[2] - s.env.data.qpos[2] >= .0002
    assert actual_stop_start(s.env.events, None) is None
    s._finish('TEST_FINAL_STOP')
    assert actual_stop_start(s.env.events, None) > .4
    assert s.env.guard_facts['contact_reasons'] == []
    assert s.env.guard_facts['motion_reasons'] == []


def test_late_guard_preserves_original_task_decision_clock(candidate_session):
    s = candidate_session
    s._finish('TIME_LIMIT')
    s.env.data.time = .2
    row = s.env.observe()
    row['contact_wrench_M'][0] = .026
    s.env._guard(row)
    s.advance_cycle([0]*4)
    assert s.stop_time == 0.
    assert s.reason == 'CONTACT_GUARD'
    assert s.env.stop_snapshot['time_s'] == 0.
