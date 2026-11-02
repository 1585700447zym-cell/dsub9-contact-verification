import numpy as np


def test_prepare_and_observe_do_not_update_controller_twice(session):
    first = session.prepare_cycle()
    state = session.controller_state_snapshot()
    for _ in range(3):
        assert session.prepare_cycle().cycle_id == first.cycle_id
        session.observe()
    assert session.controller_state_snapshot() == state
    assert len(state['history']) == 1
    session.advance_cycle(np.zeros(4))
    assert len(session.controller_state_snapshot()['history']) == 2


def test_returned_snapshots_are_independent(session):
    snapshot = session.observe()
    snapshot.base_command[2] = 999
    snapshot.state['position_m'][0] = 999
    assert session.observe().base_command[2] == .001
    assert session.observe().state['position_m'][0] == 0


def test_reset_removes_history_timers_and_old_commands(session):
    from tools.validation.run_b1_baseline import cases
    initial = session.observe()
    for _ in range(3):
        session.advance_cycle(np.zeros(4))
    session.reset(cases()[0], seed=2026092201)
    assert session.observe() == initial
    assert len(session.controller_state_snapshot()['history']) == 1
    assert session.reason is None and session.stop_time is None
    assert session.hold_start is None and session.recovery_state is None


def test_two_environments_do_not_share_cache_or_physics(session):
    from tools.learning.session import EpisodeSession
    from tools.validation.run_b1_baseline import cases
    other = EpisodeSession()
    other.reset(cases()[0], seed=7)
    session.advance_cycle(np.zeros(4))
    assert other.observe().time_s == 0
    other.advance_cycle(np.zeros(4))
    assert other.observe() == session.observe()


def test_first_cycles_match_original_runner_record_timing(session):
    import gzip
    import json
    from tools.learning.runtime import ROOT
    old = json.loads(gzip.decompress((ROOT / 'deliverables/native313_baseline_matrix/b2_v1/aligned/original.json.gz').read_bytes()))
    assert session.initial_trace_row == old['trace'][0]
    for expected in old['trace'][1:11]:
        result = session.advance_cycle(np.zeros(4))
        assert result.trace_row == expected


def test_compatibility_mode_rejects_nonzero_actions(session):
    import pytest
    with pytest.raises(ValueError, match='zero residual'):
        session.advance_cycle([1, 0, 0, 0])


def test_failed_reset_invalidates_old_snapshot_and_requires_successful_reset(session):
    from dataclasses import replace, asdict
    from types import SimpleNamespace
    from tools.validation.run_b1_baseline import cases
    import pytest
    case = cases()[0]
    for bad in [SimpleNamespace(**(asdict(case) | {'x_offset_m': float('nan')})),
                replace(case, x_offset_m=.0001, start_origin_z_m=-.0035)]:
        session.reset(case)
        session.advance_cycle([0, 0, 0, 0])
        with pytest.raises(ValueError):
            session.reset(bad)
        assert session.done
        for operation in [session.observe, session.prepare_cycle,
                          lambda: session.advance_cycle([0, 0, 0, 0])]:
            with pytest.raises(RuntimeError):
                operation()
    assert session.reset(case).time_s == 0


def test_invalid_substep_reports_elapsed_clock_not_stale_observation_time(session, monkeypatch):
    import pytest
    calls = []
    def valid_only_before_integration():
        calls.append(1)
        return len(calls) == 1
    monkeypatch.setattr(session.env, '_state_valid', valid_only_before_integration)
    result = session.advance_cycle([0, 0, 0, 0])
    assert result.done and session.reason == 'INVALID_SIMULATION'
    assert result.dt == pytest.approx(.0002)
    assert result.next_snapshot.time_s == pytest.approx(.0002)
    assert result.trace_row['time_s'] == 0  # Explicitly last finite sample, not live clock.
