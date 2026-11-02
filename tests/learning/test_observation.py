from copy import deepcopy
import math
import numpy as np
import pytest
from tools.learning.types import CycleSnapshot


def snapshot():
    state = dict(position_m=[0., 0., -.004], quaternion_wxyz=[1., 0., 0., 0.],
                 velocity_world=[0.]*6, contact_wrench_M=[.025, 0., 0., 0., .0005, 0.],
                 reference_qpos=[0., 0., -.004, 1., 0., 0., 0.],
                 limited_command_world=[0.]*6, phase='RUNNING', penetration_m=0., contact_count=0)
    controller = dict(phase='INSERT', phase_start=0., search_count=0, theta=0.,
                      search_origin=None, history=[(0., 0.)], admittance_velocity=[0.]*4,
                      admittance_offset=[0.]*4)
    return CycleSnapshot(0, 0., [0., 0., .001, 0., 0., 0.], True, state, controller)


def builder(snap):
    from tools.control.search_recovery import SearchConfig
    from tools.learning.observation import ObservationBuilder
    return ObservationBuilder(snap.state, SearchConfig())


def context():
    return dict(reason=None, recovery_state=None, recovery_count=0, hold_start=None,
                wait_start=None, actual_stop_start=None, previous_residual=[0.]*4,
                guard_facts=dict(simulation_valid=True, invalid_reasons=[], contact_reasons=[], motion_reasons=[]))


def test_wrench_history_reset_scales_and_read_only_cycle_cache():
    s = snapshot()
    b = builder(s)
    vector, raw = b.capture(s, context())
    np.testing.assert_array_equal(vector[b.slices['wrench_history_M']], [1, 0, 0, 0, 1, 0]*4)
    s1 = deepcopy(s)
    s1.cycle_id = 1
    s1.time_s = .002
    s1.state['contact_wrench_M'][0] = .0125
    v1, r1 = b.capture(s1, context())
    assert r1['wrench_history_M'][0] == .0125  # newest first
    np.testing.assert_array_equal(v1[b.slices['wrench_history_M']][6:], vector[b.slices['wrench_history_M']][:18])
    for _ in range(3):
        v2, r2 = b.capture(s1, context())
        np.testing.assert_array_equal(v1, v2)
        assert r1 == r2
    r2['wrench_history_M'][0] = 999
    assert b.capture(s1, context())[1]['wrench_history_M'][0] == .0125


def test_privileged_labels_and_common_translation_do_not_enter_policy():
    s = snapshot()
    expected = builder(s).capture(s, context())[0]
    altered = deepcopy(s)
    altered.privileged_evaluation = {'hole_center': [9, 8, 7], 'initial_error': 'secret'}
    altered.state.update(penetration_m=999, contact_count=999, true_hole_error=[100]*3)
    altered.state['position_m'] = [1., 2., 3.]
    altered.state['reference_qpos'][:3] = [1., 2., 3.]
    actual = builder(altered).capture(altered, context())[0]
    np.testing.assert_array_equal(actual, expected)


def test_rotation_vector_is_world_relative_and_sign_invariant():
    from tools.learning.observation import rotation_vector_world
    a = math.sqrt(.5)
    # initial=90deg Z; current = 90deg X * initial => world-relative 90deg X.
    initial, current = [a, 0, 0, a], [.5, .5, -.5, .5]
    np.testing.assert_allclose(rotation_vector_world(initial, current), [math.pi/2, 0, 0], atol=1e-14)
    np.testing.assert_allclose(rotation_vector_world(initial, -np.array(current)), [math.pi/2, 0, 0], atol=1e-14)
    with pytest.raises(ValueError):
        rotation_vector_world(initial, [0]*4)


def test_known_controller_state_is_visible_with_validity_bits():
    s = snapshot()
    s.controller_state.update(phase='SEARCH', search_origin=[.0001, -.0002, .002],
                              history=[(0., 0.), (.4, .000002)], phase_start=.2, search_count=1, theta=2.)
    s.time_s = .4
    s.state['position_m'][2] += .000002
    ctx = context()
    ctx.update(wait_start=.3, actual_stop_start=.1, hold_start=.35)
    b = builder(snapshot())
    v, raw = b.capture(s, ctx)
    assert raw['search_origin_m'] == [.0001, -.0002, .002]
    assert raw['search_origin_valid'] == [1.]
    assert raw['stall_progress_m'] == pytest.approx([.000002], abs=1e-15)
    assert raw['stall_span_s'] == [.4]
    assert raw['stop_elapsed_s'] == pytest.approx([.3])
    assert raw['wait_elapsed_s'] == pytest.approx([.1])
    assert raw['hold_elapsed_s'] == pytest.approx([.05])
    assert np.isfinite(v).all()


def test_missing_optional_state_zeroes_have_explicit_validity():
    s = snapshot()
    b = builder(s)
    _, raw = b.capture(s, context())
    for name in ('search_origin', 'search_budget', 'hold', 'stop', 'wait'):
        assert raw[name + '_valid'] == [0.]


def test_normalization_clips_only_policy_not_raw_measurement():
    s = snapshot()
    s.state['contact_wrench_M'][0] = 1.
    b = builder(s)
    vector, raw = b.capture(s, context())
    assert vector[b.slices['wrench_history_M']][0] == 10.
    assert raw['wrench_history_M'][0] == 1.
    assert s.state['contact_wrench_M'][0] == 1.


def test_nonfinite_observable_is_rejected_not_zero_filled():
    s = snapshot()
    s.state['velocity_world'][0] = float('nan')
    with pytest.raises(ValueError):
        builder(s).capture(s, context())


@pytest.mark.parametrize('value', [float('nan'), float('inf')])
@pytest.mark.parametrize('field', ['time_s', 'phase_start', 'hold_start', 'wait_start', 'actual_stop_start', 'history_time'])
def test_nonfinite_source_timers_cannot_be_clamped_into_valid_zeros(field, value):
    s, ctx = snapshot(), context()
    if field == 'time_s':
        s.time_s = value
    elif field == 'phase_start':
        s.controller_state['phase_start'] = value
    elif field == 'history_time':
        s.controller_state['history'] = [(value, 0.)]
    else:
        ctx[field] = value
    with pytest.raises(ValueError):
        builder(s).capture(s, ctx)


@pytest.mark.parametrize('change', [
    {'theta': [0., 0.], 'search_origin': [0., 0.]},
    {'theta': [0.]}, {'search_origin': [[0., 0., 0.]]},
    {'search_count': float('nan')},
])
def test_field_shapes_cannot_shift_semantics_even_if_total_width_matches(change):
    s = snapshot()
    s.controller_state.update(change)
    with pytest.raises(ValueError):
        builder(s).capture(s, context())
