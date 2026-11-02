"""Analytic fixtures, no actor evaluations, random draws or optimizer calls."""
import importlib
import math
import pytest


def api():
    return importlib.import_module('tools.learning.policy_distribution_diagnostics')


def test_identical_standard_gaussians_have_zero_kl_and_known_tail_probability():
    r = api().diagnose([0.]*4, [0.]*4, [0.]*4, [0.]*4)
    assert r['deterministic_actions'] == [0.]*4
    assert r['kl_to_reference_per_axis'] == pytest.approx([0.]*4, abs=1e-12)
    # Independent Simpson integration of the normal PDF gives 0.066984081448.
    assert r['saturation_probability_per_axis'] == pytest.approx([.066984081448]*4, abs=1e-12)


def test_same_deterministic_action_can_have_very_different_random_saturation():
    narrow = api().diagnose([0.]*4, [0.]*4, [0.]*4, [-2.]*4)
    broad = api().diagnose([0.]*4, [0.]*4, [0.]*4, [1.]*4)
    assert narrow['deterministic_actions'] == broad['deterministic_actions'] == [0.]*4
    assert max(narrow['saturation_probability_per_axis']) < 1e-20
    assert min(broad['saturation_probability_per_axis']) > .49


def test_shifted_mean_kl_and_tail_are_not_mistaken_for_safety():
    r = api().diagnose([0.]*4, [0.]*4, [2.]*4, [0.]*4)
    assert r['kl_to_reference_per_axis'] == pytest.approx([2.]*4)
    assert r['deterministic_actions'] == pytest.approx([.9640275801]*4)
    assert min(r['saturation_probability_per_axis']) > .56


def test_non_unit_variance_kl_locks_candidate_to_reference_direction():
    # KL(N(0,4)||N(0,1)) = 1.5-ln(2); reverse = ln(2)-.375.
    broad = api().diagnose([0.]*4, [0.]*4, [0.]*4, [math.log(2)]*4)
    narrow = api().diagnose([0.]*4, [math.log(2)]*4, [0.]*4, [0.]*4)
    assert broad['kl_to_reference_per_axis'] == pytest.approx([.8068528194400547]*4)
    assert narrow['kl_to_reference_per_axis'] == pytest.approx([.3181471805599453]*4)


@pytest.mark.parametrize('bad', [[], [0.]*3, [0.,0.,0.,float('nan')], [0.,0.,0.,True], [0.,0.,0.,'0']])
def test_malformed_distribution_parameters_are_rejected(bad):
    with pytest.raises(ValueError): api().diagnose([0.]*4, [0.]*4, bad, [0.]*4)


@pytest.mark.parametrize('value', [-21., 3., float('inf')])
def test_outside_locked_sb3_log_std_range_is_rejected(value):
    with pytest.raises(ValueError): api().diagnose([0.]*4, [0.]*4, [0.]*4, [value]*4)


def test_numeric_overflow_is_rejected_instead_of_reported_as_valid_kl():
    with pytest.raises(ValueError): api().diagnose([0.]*4, [0.]*4, [1e308]*4, [0.]*4)


def test_state_selection_keeps_original_index_order_and_includes_endpoints():
    rows = [dict(action_active=i%2 == 0, observation=[float(i)]*120) for i in range(20)]
    selected = api().select_state_indices(rows, count=4)
    assert selected == [0, 6, 12, 18]
    assert rows[18]['observation'][0] == 18.


def test_selection_refuses_duplicates_short_data_and_numeric_permission():
    m = api()
    with pytest.raises(ValueError): m.select_state_indices([dict(action_active=True)]*3, count=4)
    with pytest.raises(ValueError): m.select_state_indices([dict(action_active=1)]*10, count=4)
    with pytest.raises(ValueError): m.select_state_indices([dict(action_active=True)]*10, count=True)
