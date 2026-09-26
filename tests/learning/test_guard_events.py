"""Guard logic counterexamples; injected rows are NOT dynamics evidence."""
from dataclasses import replace
import math
import numpy as np
import pytest


def candidate_config():
    from tools.learning.guarded_environment import GuardCandidateConfig
    return GuardCandidateConfig(max_rotation_from_start_rad=math.radians(2.5),
                                initial_roll_pitch_limit_rad=math.radians(1.5))


@pytest.fixture
def guarded(runtime):
    from tools.learning.guarded_environment import LearningEnvironment
    from tools.validation.run_b1_baseline import cases
    env = LearningEnvironment(guard_config=candidate_config())
    env.reset(cases()[0])
    return env


def roll_quaternion(degrees):
    a = math.radians(degrees) / 2
    return [math.cos(a), math.sin(a), 0., 0.]


def test_no_implicit_or_nonfinite_rotation_limit(runtime):
    from tools.learning.guarded_environment import GuardCandidateConfig, LearningEnvironment
    with pytest.raises(TypeError):
        LearningEnvironment()
    for x in (0, -1, float('inf'), float('nan'), math.pi + .1):
        with pytest.raises(ValueError):
            GuardCandidateConfig(max_rotation_from_start_rad=x,
                                 initial_roll_pitch_limit_rad=.02)


def test_relative_rotation_not_absolute_euler_or_quaternion_sign(guarded):
    from tools.learning.guarded_environment import relative_rotation_rad
    q0 = roll_quaternion(1.5)
    assert relative_rotation_rad(q0, -np.array(q0)) == pytest.approx(0., abs=1e-12)
    assert relative_rotation_rad(q0, roll_quaternion(4.)) == pytest.approx(math.radians(2.5), abs=1e-12)
    with pytest.raises(ValueError):
        relative_rotation_rad(q0, [0, 0, 0, 0])


def test_rotation_boundary_uses_actual_row_and_stops_without_invalidating(guarded):
    row = guarded.observe()
    row['quaternion_wxyz'] = roll_quaternion(2.499)
    guarded._guard(row)
    assert guarded.phase == 'RUNNING'
    row['quaternion_wxyz'] = roll_quaternion(2.501)
    guarded._guard(row)
    assert guarded.phase == 'STOPPING'
    assert guarded.guard_facts['simulation_valid'] is True
    assert guarded.guard_facts['motion_reasons'] == ['ROTATION_LIMIT']
    assert guarded.guard_facts['max_rotation_from_start_rad'] > math.radians(2.5)


def test_same_substep_collects_invalid_contact_and_motion(guarded):
    row = guarded.observe()
    row['penetration_m'] = 90e-6
    row['contact_wrench_M'] = [.026, 0, 0, 0, 0, 0]
    row['contact_wrench_G'] = [0, 0, 0, .0006, 0, 0]
    row['quaternion_wxyz'] = roll_quaternion(2.6)
    row['velocity_world'] = [.021, 0, 0, 0, .51, 0]
    row['position_m'][0] += .007
    guarded._guard(row)
    facts = guarded.guard_facts
    assert facts['simulation_valid'] is False
    assert set(facts['contact_reasons']) == {'FORCE_LIMIT', 'TORQUE_LIMIT', 'PENETRATION_LIMIT'}
    assert set(facts['motion_reasons']) == {'ROTATION_LIMIT', 'SPEED_LIMIT', 'ANGULAR_SPEED_LIMIT', 'TRAVEL_LIMIT'}
    assert guarded.phase == 'TERMINAL'
    assert 'INVALID_PENETRATION' in facts['invalid_reasons']


def test_first_contact_limit_during_stopping_latches_without_clock_restart(guarded):
    guarded.stop('REQUESTED_STOP')
    row = guarded.observe()
    guarded.data.time = row['time_s'] = .2
    row['contact_wrench_M'] = [.026, 0, 0, 0, 0, 0]
    guarded._guard(row)
    guarded._guard(row)
    from tools.validation.native313_matrix_audit import actual_stop_start
    assert actual_stop_start(guarded.events, None) == 0.
    assert guarded.stop_snapshot['time_s'] == 0.
    assert guarded.guard_facts['contact_reasons'] == ['FORCE_LIMIT']
    events = [e for e in guarded.events if 'FORCE_LIMIT' in e['reason']]
    assert len(events) == 1 and events[0]['time_s'] == .2


def test_latched_motion_blocks_recovery_even_after_state_returns_inside(guarded):
    row = guarded.observe()
    row['quaternion_wxyz'] = roll_quaternion(2.6)
    guarded._guard(row)
    with pytest.raises(RuntimeError):
        guarded.request_recovery()
    assert guarded.recovery_count == 0


def test_reset_clears_facts_and_rejected_initial_pose_cannot_reuse_old_episode(guarded):
    from tools.validation.run_b1_baseline import cases
    row = guarded.observe()
    row['quaternion_wxyz'] = roll_quaternion(2.6)
    guarded._guard(row)
    guarded.reset(cases()[0])
    assert guarded.guard_facts['motion_reasons'] == []
    with pytest.raises(ValueError):
        guarded.reset(replace(cases()[0], roll_rad=math.radians(1.6)))
    assert guarded.phase == 'TERMINAL'
    assert guarded.guard_facts['simulation_valid'] is False
    with pytest.raises(RuntimeError):
        guarded.step(np.zeros(6))


def test_live_engine_invalidity_retains_other_finite_facts(guarded):
    # The frozen loop terminates before _guard when a live warning is present.
    guarded.data.qvel[0] = .021
    guarded.data.warning[0].number = 1
    guarded.step(np.zeros(6))
    assert guarded.phase == 'TERMINAL'
    assert guarded.guard_facts['simulation_valid'] is False
    assert 'SPEED_LIMIT' in guarded.guard_facts['motion_reasons']


def test_substeps_and_snapshots_are_instance_local_and_candidate_is_not_admission(guarded):
    from tools.learning.guarded_environment import LearningEnvironment
    from tools.validation.run_b1_baseline import cases
    other = LearningEnvironment(guard_config=candidate_config())
    other.reset(cases()[0])
    guarded.step(np.zeros(6))
    assert guarded.guard_facts['checked_substeps'] == 10
    assert other.guard_facts['checked_substeps'] == 0
    copy = guarded.guard_facts
    copy['motion_reasons'].append('FAKE')
    assert guarded.guard_facts['motion_reasons'] == []
    assert guarded.metadata()['training_admitted'] is False


def test_rejected_reset_does_not_expose_previous_episode_statistics(guarded):
    from tools.validation.run_b1_baseline import cases
    guarded.stop('REQUESTED_STOP')
    guarded.step(np.zeros(6))
    assert guarded.stop_samples
    with pytest.raises(ValueError):
        guarded.reset(replace(cases()[0], roll_rad=math.radians(1.6)))
    with pytest.raises(RuntimeError):
        guarded.observe()
    assert guarded.stop_samples == []
    assert guarded.cycle_peaks['samples'] == 0
    assert guarded.peaks == {}
