"""Pure command/state-machine tests: no model construction or physics steps."""
import copy
import math
from types import SimpleNamespace

import numpy as np
import pytest

from tools.validation.run_actor_lr_comparison import select_qualified_runtime

# Select the already-qualified package before importing the dynamics module.
# This verifies/imports the package only; no model or environment is created.
select_qualified_runtime()

from tools.control.search_recovery import Observation, SearchRecovery, resume_after_recovery
from tools.control.load_search import LoadSearchRecovery
from tools.control.reference_search import DriveObservation, ReferenceSearchRecovery
from tools.control.risk_search import PoseObservation
from tools.dynamics.cartesian import CartesianEnvironment, DynamicConfig


class TimeBudgetSearch(SearchRecovery):
    def search_count_exhausted(self):
        return False


class TimeBudgetLoad(LoadSearchRecovery):
    def search_count_exhausted(self):
        return False


class TimeBudgetReference(ReferenceSearchRecovery):
    def search_count_exhausted(self):
        return False


class TimeBudgetCartesian(CartesianEnvironment):
    def recovery_count_exhausted(self):
        return False


def observation(t, fz=0.):
    return Observation(t, (0., 0., 0.), (0., 0., fz, 0., 0., 0.))


def logical_environment(cls=TimeBudgetCartesian):
    """Exercise production recovery methods with finite buffers, not MuJoCo."""
    env = object.__new__(cls)
    env.config = DynamicConfig(collision_backend='native', stop_force_N=5.,
                              stop_torque_Nm=.1, recovery_force_N=.5)
    q = np.array([0., 0., 0., 1., 0., 0., 0.])
    env.data = SimpleNamespace(time=1., qpos=q.copy(), qvel=np.zeros(6), qacc=np.zeros(6),
        qfrc_constraint=np.zeros(6), qfrc_applied=np.zeros(6), xpos=np.array([q[:3]]),
        xmat=np.eye(3).reshape(1, 9), contact=SimpleNamespace(dist=np.array([])), warning=[])
    env.initial = q.copy()
    env.reference = q.copy()
    env.command = np.ones(6)*1e-6
    env.raw_command = env.command.copy()
    env.phase = 'STOPPING'
    env.recovery_count = 0
    env.recovery_start = None
    env.events = [dict(time_s=1., phase='STOPPING', reason='B2_SEARCH_EXHAUSTED')]
    env.peaks = dict(force_N=0., torque_G_Nm=0., penetration_m=0.)
    env.guard_facts = dict(simulation_valid=True, invalid_reasons=[], contact_reasons=[], motion_reasons=[])
    env.last_finite = dict(time_s=1., position_m=q[:3].tolist(), velocity_world=[0.]*6,
        contact_wrench_M=[0.]*6, contact_wrench_G=[0.]*6, penetration_m=0.)
    return env


def complete_retraction(env):
    """Supply a hand-specified completed recovery; never integrate or step."""
    env.data.time += .55
    env.data.qpos[2] -= .00025
    env.last_finite.update(time_s=env.data.time, position_m=env.data.qpos[:3].tolist())
    env.stop('RECOVERY_DISTANCE_REACHED')


def begin_next_recovery(env):
    env.data.time += .1
    env.stop('B2_SEARCH_EXHAUSTED')
    env.request_recovery()
    complete_retraction(env)


def completed_recovery(number=1):
    env = logical_environment()
    env.request_recovery()
    complete_retraction(env)
    for _ in range(number-1):
        resume_after_recovery(env, .0002, unlimited_recoveries=True)
        begin_next_recovery(env)
    return env


def test_default_search_still_ends_on_second_search():
    c = SearchRecovery()
    c.search_count = 2
    c.phase = 'WAIT_RECOVERY'
    with pytest.raises(RuntimeError):
        c.start_recovered_search(observation(2.))
    c._start_search(observation(2.))
    c.theta = 2*math.pi*c.config.spiral_radius_m/c.config.spiral_pitch_m
    c.command(observation(2.002), .002)
    assert c.phase == 'FAILED' and c.reason == 'SEARCH_BUDGET_EXHAUSTED'


def test_search_hook_allows_third_and_fourth_search_without_changing_deadline():
    c = TimeBudgetSearch()
    config = c.config
    c.search_count = 2
    c.phase = 'WAIT_RECOVERY'
    for count in (3, 4):
        c.start_recovered_search(observation(float(count)))
        assert c.phase == 'SEARCH' and c.search_count == count
        c.theta = 2*math.pi*c.config.spiral_radius_m/c.config.spiral_pitch_m
        c.command(observation(count+.002), .002)
        assert c.phase == 'WAIT_RECOVERY'
        assert c.events[-1]['reason'] == 'SEARCH_EXHAUSTED'
    assert c.config is config and c.config.total_action_time_s == 20.


def test_search_hook_keeps_axial_stall_unload_after_second_search():
    c = TimeBudgetSearch()
    c.search_count = 2
    c.command(observation(.6, -.02), .002)
    command = c.command(observation(1., -.02), .002)
    assert c.phase == 'UNLOAD' and command[2] < 0.
    assert c.events[-1]['reason'] == 'AXIAL_STALL'


def test_search_hook_does_not_bypass_actual_excursion_guard():
    c = TimeBudgetSearch()
    c._start_search(observation(0.))
    c.search_count = 3
    command = c.command(Observation(.1, (.001, 0., 0.), (0.,)*6), .002)
    assert c.phase == 'FAILED' and c.reason == 'SEARCH_EXCURSION_LIMIT'
    assert np.array_equal(command, np.zeros(6))


def test_load_relief_uses_search_hook_after_second_search():
    c = TimeBudgetLoad()
    sample = PoseObservation(.1, (0.,)*3, (.022, 0., -.008, 0., 0., 0.), 0.)
    c._start_search(PoseObservation(0., (0.,)*3, (0.,)*6, 0.))
    c.search_count = 2
    c.command(sample, .002)
    c.command(PoseObservation(.12, sample.displacement_m, sample.wrench_M, 0.), .002)
    assert c.phase == 'UNLOAD' and c.reference_release_requested
    assert c.events[-1]['reason'] == 'SEARCH_LATERAL_LOAD'


def test_reference_boundary_uses_search_hook_after_second_search():
    c = TimeBudgetReference()
    c._start_search(DriveObservation(0., (0.,)*3, (0.,)*6, 0., (0.,)*3, (0., 0.)))
    c.search_count = 2
    command = c.command(DriveObservation(.2, (0.,)*3, (0.,)*6, 0.,
        (119.99e-6, 0., 0.), (.0003, 0.)), .002)
    assert c.phase == 'WAIT_RECOVERY' and np.array_equal(command, np.zeros(6))
    assert c.events[-1]['reason'] == 'SEARCH_EXHAUSTED'
    assert c.events[-1]['reference_boundary_end']


def test_default_physical_layer_still_rejects_second_recovery():
    env = logical_environment(CartesianEnvironment)
    env.request_recovery()
    complete_retraction(env)
    resume_after_recovery(env, .0002)
    env.data.time += .1
    env.stop('B2_SEARCH_EXHAUSTED')
    with pytest.raises(RuntimeError):
        env.request_recovery()
    assert env.recovery_count == 1 and env.phase == 'STOPPING'


def test_physical_hook_and_explicit_resume_allow_three_completed_recoveries():
    env = logical_environment()
    for count in (1, 2, 3):
        if count == 1:
            env.request_recovery()
            complete_retraction(env)
        else:
            begin_next_recovery(env)
        q, v = env.data.qpos.copy(), env.data.qvel.copy()
        time, peaks, facts = env.data.time, copy.deepcopy(env.peaks), copy.deepcopy(env.guard_facts)
        events = copy.deepcopy(env.events)
        resume_after_recovery(env, .0002, unlimited_recoveries=True)
        assert env.recovery_count == count and env.phase == 'RUNNING'
        assert np.array_equal(env.data.qpos, q) and np.array_equal(env.data.qvel, v)
        assert env.data.time == time and env.peaks == peaks and env.guard_facts == facts
        assert env.events[:-1] == events
        assert env.events[-1]['reason'] == 'B2_RECOVERY_RESUMED'
        assert np.array_equal(env.reference, q) and np.array_equal(env.command, np.zeros(6))


def test_second_resume_requires_explicit_opt_in():
    env = completed_recovery(2)
    with pytest.raises(RuntimeError):
        resume_after_recovery(env, .0002)
    assert env.phase == 'STOPPING'


def test_completed_recovery_cannot_be_resumed_twice():
    env = completed_recovery(2)
    resume_after_recovery(env, .0002, unlimited_recoveries=True)
    before = copy.deepcopy(env.events)
    with pytest.raises(RuntimeError):
        resume_after_recovery(env, .0002, unlimited_recoveries=True)
    assert env.phase == 'RUNNING' and env.events == before


@pytest.mark.parametrize('fault', [
    'old_hard_stop', 'latest_hard_stop', 'missing_accept', 'count_mismatch',
    'accept_time_mismatch', 'reverse_time', 'future_event', 'distance',
    'linear_speed', 'angular_speed', 'force', 'torque', 'penetration',
    'peak_force', 'peak_torque', 'peak_penetration', 'invalid_state',
    'invalid_fact', 'contact_fact', 'motion_fact', 'simulation_fact',
])
def test_unlimited_resume_rejects_unsafe_or_incomplete_segments_without_mutation(fault):
    env = completed_recovery(2)
    if fault == 'old_hard_stop': env.events[0]['reason'] = 'FORCE_LIMIT'
    if fault == 'latest_hard_stop': env.events[-1]['reason'] = 'RECOVERY_TIME_LIMIT'
    if fault == 'missing_accept': del env.events[-2]
    if fault == 'count_mismatch': env.recovery_count += 1
    if fault == 'accept_time_mismatch': env.recovery_start_time -= .01
    if fault == 'reverse_time': env.events[-1]['time_s'] = env.events[-2]['time_s']-.01
    if fault == 'future_event': env.events[-1]['time_s'] = env.data.time+.01
    if fault == 'distance': env.data.qpos[2] = env.recovery_start[2]-.000199
    if fault == 'linear_speed': env.last_finite['velocity_world'][0] = 1.01e-5
    if fault == 'angular_speed': env.last_finite['velocity_world'][3] = .00101
    if fault == 'force': env.last_finite['contact_wrench_M'][0] = .501
    if fault == 'torque': env.last_finite['contact_wrench_G'][3] = .101
    if fault == 'penetration': env.last_finite['penetration_m'] = 30e-6
    if fault == 'peak_force': env.peaks['force_N'] = 5.01
    if fault == 'peak_torque': env.peaks['torque_G_Nm'] = .101
    if fault == 'peak_penetration': env.peaks['penetration_m'] = 31e-6
    if fault == 'invalid_state': env.data.qpos[0] = float('nan')
    if fault == 'invalid_fact': env.guard_facts['invalid_reasons'] = ['INVALID_SIMULATION']
    if fault == 'contact_fact': env.guard_facts['contact_reasons'] = ['FORCE_LIMIT']
    if fault == 'motion_fact': env.guard_facts['motion_reasons'] = ['ROTATION_LIMIT']
    if fault == 'simulation_fact': env.guard_facts['simulation_valid'] = False
    before = copy.deepcopy(env.__dict__)
    with pytest.raises(RuntimeError):
        resume_after_recovery(env, .0002, unlimited_recoveries=True)
    assert env.phase == before['phase'] and env.events == before['events']
    assert np.array_equal(env.data.qpos, before['data'].qpos, equal_nan=True)
    assert env.data.time == before['data'].time and env.guard_facts == before['guard_facts']


@pytest.mark.parametrize('minimum', [0., -.0002, float('nan'), float('inf')])
def test_unlimited_resume_requires_finite_positive_actual_retraction_threshold(minimum):
    env = completed_recovery()
    with pytest.raises(ValueError):
        resume_after_recovery(env, minimum, unlimited_recoveries=True)


def test_unlimited_resume_requires_explicit_boolean():
    env = completed_recovery()
    with pytest.raises(ValueError):
        resume_after_recovery(env, .0002, unlimited_recoveries='yes')
