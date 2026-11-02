import pytest


def test_same_version_comparison_rejects_guard_or_state_changes():
    from tools.validation.verify_residual_observation import compare_candidate
    reference = dict(trace=[{'position_m': [0., 0., -.004]}], events=[],
        physical_stop_samples=[], guard_facts={'simulation_valid': True},
        outcome={'training_admitted': False}, physical_steps=10)
    compare_candidate(reference, reference)
    with pytest.raises(AssertionError):
        compare_candidate(dict(reference, guard_facts={'simulation_valid': False}), reference)
    with pytest.raises(AssertionError):
        compare_candidate(dict(reference, trace=[]), reference)
