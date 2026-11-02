"""Search exhaustion is recoverable; an already-invalid reference is not."""
import math
import numpy as np
import pytest

REFERENCE = (0.00010695684626314158, -0.00005436250121519483)
PREVIOUS = (0.00008962780032265731, 0.00011967426982662896)
THETA = 18.35047292124969


def controller_and_sample(search_count=1):
    from tools.control.reference_search import ReferenceSearchRecovery, DriveObservation
    c = ReferenceSearchRecovery()
    origin = DriveObservation(2., (0., 0., 0.), (0., 0., -.008, 0., 0., 0.), 0.,
                              (0., 0., 0.), (0., 0.))
    c._start_search(origin)
    c.search_count = search_count
    c.theta = THETA
    sample = DriveObservation(8.756, (0., 0., 0.), origin.wrench_M, 0.,
                              (*REFERENCE, 0.), PREVIOUS)
    return c, sample


@pytest.mark.parametrize('count,phase,reason', [
    (1, 'WAIT_RECOVERY', 'SEARCH_EXHAUSTED'),
    (2, 'FAILED', 'SEARCH_BUDGET_EXHAUSTED'),
])
def test_recorded_infeasible_next_step_ends_search_without_spending_extra_retry(count, phase, reason):
    c, sample = controller_and_sample(count)
    before_offset = c.admittance.offset.copy()
    before_velocity = c.admittance.velocity.copy()
    command = c.command(sample, .002)
    assert c.phase == phase and c.events[-1]['reason'] == reason
    assert c.events[-1]['reference_boundary_end'] is True
    assert c.events[-1]['reference_boundary_final_segment'] is False
    assert c.search_count == count and c.search_composition is None
    np.testing.assert_array_equal(command, np.zeros(6))
    np.testing.assert_array_equal(c.admittance.offset, before_offset)
    np.testing.assert_array_equal(c.admittance.velocity, before_velocity)


def test_continuation_predictor_matches_the_actual_controlled_end_before_final_segment():
    from tools.learning.v4_continuation import predict_next_search
    c, sample = controller_and_sample()
    result = predict_next_search(REFERENCE, PREVIOUS, THETA, c.config, .002)
    assert result['reference_feasible'] and result['controlled_search_end']
    assert np.linalg.norm(result['predicted_reference_xy_m']) > c.config.spiral_radius_m
    assert THETA < c.config.spiral_radius_m / (c.config.spiral_pitch_m / (2 * math.pi))
    c.command(sample, .002)
    assert c.phase == 'WAIT_RECOVERY'


def test_current_reference_violation_is_still_a_reference_fault():
    from dataclasses import replace
    from tools.learning.v4_continuation import predict_next_search
    c, sample = controller_and_sample()
    invalid = (121e-6, 0.)
    result = predict_next_search(invalid, (0., 0.), THETA, c.config, .002)
    assert not result['reference_feasible'] and not result['controlled_search_end']
    c.command(replace(sample, reference_displacement_m=(*invalid, 0.)), .002)
    assert c.phase == 'FAILED' and c.reason == 'SEARCH_REFERENCE_LIMIT'
    assert not c.events[-1].get('reference_boundary_end', False)


def test_interior_search_keeps_its_command_and_advances_admittance_once():
    from dataclasses import replace
    c, sample = controller_and_sample()
    c.theta = 8.
    command = c.command(replace(sample, reference_displacement_m=(0., 0., 0.),
                                previous_command_xy_m_s=(0., 0.)), .002)
    assert c.phase == 'SEARCH' and c.events[-1]['reason'] == 'LOW_LOAD_SEARCH'
    assert not c.events[-1].get('reference_boundary_end', False)
    assert np.isfinite(command).all() and c.search_composition is not None


@pytest.mark.parametrize('branch', ['advance', 'search_timeout', 'spiral_end'])
def test_current_reference_fault_precedes_normal_search_phase_changes(branch):
    from dataclasses import replace
    c, sample = controller_and_sample()
    sample = replace(sample, reference_displacement_m=(121e-6, 0., 0.))
    if branch == 'advance': sample = replace(sample, displacement_m=(0., 0., .00015))
    if branch == 'search_timeout': sample = replace(sample, time_s=2.+c.config.search_time_s)
    if branch == 'spiral_end': c.theta=c.config.spiral_radius_m/(c.config.spiral_pitch_m/(2*math.pi))
    c.command(sample, .002)
    assert c.phase == 'FAILED' and c.reason == 'SEARCH_REFERENCE_LIMIT'
    assert c.search_count == 1 and c.events[-1]['reason'] == 'SEARCH_REFERENCE_LIMIT'
    assert not c.events[-1].get('reference_boundary_end', False)


@pytest.mark.parametrize('bad', ['position', 'wrench', 'time', 'angle', 'dt_zero', 'dt_inf'])
def test_invalid_sensor_or_period_is_rejected_before_reference_fault_mutates_state(bad):
    from dataclasses import replace
    from copy import deepcopy
    c, sample = controller_and_sample()
    sample=replace(sample, reference_displacement_m=(121e-6, 0., 0.));dt=.002
    if bad=='position': sample=replace(sample, displacement_m=(0.,float('nan'),0.))
    if bad=='wrench': sample=replace(sample, wrench_M=(0.,0.,float('nan'),0.,0.,0.))
    if bad=='time': sample=replace(sample,time_s=float('nan'))
    if bad=='angle': sample=replace(sample,relative_rotation_rad=float('nan'))
    if bad=='dt_zero': dt=0.
    if bad=='dt_inf': dt=float('inf')
    before=deepcopy(c.events)
    with pytest.raises(ValueError): c.command(sample,dt)
    assert c.phase=='SEARCH' and c.events==before and c.search_count==1
