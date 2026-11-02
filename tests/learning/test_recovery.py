"""Session integration branch tests; engineered starts are not natural task success."""
import numpy as np


def recovery_ready_controller():
    from tools.control.search_recovery import SearchRecovery, SearchConfig
    controller = SearchRecovery(SearchConfig(search_time_s=.002))
    # Deterministically exhausted first search, with zero load at the approach pose.
    controller.phase = 'SEARCH'
    controller.search_count = 1
    controller.search_origin = np.zeros(3)
    controller.phase_start = -.01
    return controller


def test_session_runs_actual_retraction_then_resumes_second_search(runtime):
    from tools.learning.session import EpisodeSession
    from tools.validation.run_b1_baseline import cases
    session = EpisodeSession(controller_factory=recovery_ready_controller)
    session.reset(cases()[0], seed=1)
    assert session.recovery_state == 'WAIT_STOP'
    assert not session.observe().residual_enabled
    saw_retract = False
    for _ in range(1000):
        session.advance_cycle([0, 0, 0, 0])
        if session.env.phase == 'RETRACT':
            saw_retract = True
            assert not session.observe().residual_enabled
        if session.controller.search_count == 2:
            break
    assert saw_retract and session.env.recovery_count == 1
    assert session.controller.search_count == 2
    assert session.env.recovery_start[2] - session.env.data.qpos[2] >= .0002
    assert session.env.events[-1]['reason'] == 'B2_RECOVERY_RESUMED'
    assert session.env.phase == 'RUNNING' and session.observe().residual_enabled


def test_wait_resume_rejects_insufficient_actual_retraction(session):
    session.env.stop('B2_SEARCH_EXHAUSTED')
    session.env.request_recovery()
    session.env.stop('RECOVERY_DISTANCE_REACHED')
    # A reference-distance event without any real retraction must not resume.
    session.recovery_state = 'WAIT_RESUME'
    session.wait_start = 0
    session._cache = None
    snapshot = session.prepare_cycle()
    assert session.reason == 'RECOVERY_RESUME_REJECTED'
    assert session.env.phase == 'STOPPING' and not snapshot.residual_enabled


def test_wait_stop_timeout_does_not_retry_or_reset_stop_segment(session):
    session.env.stop('B2_SEARCH_EXHAUSTED')
    initial_stop = session.env.stop_snapshot['time_s']
    session.recovery_state = 'WAIT_STOP'
    session.wait_start = -2.
    # Controlled finite sensor sample isolates the timeout branch from dynamics.
    session.env.last_finite['velocity_world'] = [.0001, 0, 0, 0, 0, 0]
    session._cache = None
    snapshot = session.prepare_cycle()
    assert session.reason == 'RECOVERY_NOT_STABLE'
    assert session.env.recovery_count == 0 and not snapshot.residual_enabled
    assert session.env.stop_snapshot['time_s'] == initial_stop


def test_latched_historical_load_prevents_recovery(session):
    session.env.stop('B2_SEARCH_EXHAUSTED')
    session.env.peaks['force_N'] = .026
    session.recovery_state = 'WAIT_STOP'
    session.wait_start = 0
    session._cache = None
    session.prepare_cycle()
    assert session.env.recovery_count == 0
    assert not session.observe().residual_enabled
    session.advance_cycle([0, 0, 0, 0])
    assert session.reason == 'FORCE_LIMIT'
    assert session.guard_latched and session.recovery_state is None


def test_invalid_live_state_during_recovery_is_finalized_with_original_reason(session, monkeypatch):
    session.env.stop('B2_SEARCH_EXHAUSTED')
    session.recovery_state = 'WAIT_STOP'
    session.wait_start = 0
    session._cache = None
    # Cached finite sensors pass wait checks, but native live state becomes invalid.
    monkeypatch.setattr(session.env, '_state_valid', lambda: False)
    snapshot = session.prepare_cycle()
    assert session.done and session.task_finished
    assert session.reason == 'INVALID_SIMULATION'
    assert snapshot.state['phase'] == 'TERMINAL'
    assert snapshot.residual_enabled is False
