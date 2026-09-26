import pytest


def test_comparator_rejects_missing_and_changed_fields():
    from tools.validation.verify_zero_residual_session import compare_exact
    compare_exact({'command': [0., .001]}, {'command': [0., .001]}, 'cycle 1')
    with pytest.raises(AssertionError, match='cycle 1'):
        compare_exact({'command': [0., .001]}, {'command': [0., .00100001]}, 'cycle 1')
    with pytest.raises(AssertionError):
        compare_exact({'phase': 'STOPPING'}, {}, 'missing')


def test_case_selector_never_loads_independent_test_set():
    from tools.validation.verify_zero_residual_session import development_case_paths
    paths = development_case_paths()
    assert len(paths) == 7
    assert set(p.name for p in paths) == {'aligned', 'combined_a', 'combined_a_scale_0.75',
                                         'combined_b_scale_0.75', 'roll_pos_1.5deg',
                                         'x_offset_pos_100um', 'y_offset_neg_100um'}
