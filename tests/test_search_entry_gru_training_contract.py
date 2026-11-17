import pytest

from tools.learning.recovery_learning_contract import experiment_config, validate_config, verify_training_registration


def test_focused_replay_has_a_distinct_registration_without_changing_physics_or_network():
    plain = experiment_config("gru", physical_protocol="load_warning_7pct")
    focused = experiment_config("gru", physical_protocol="load_warning_7pct", focus_search_entry=True)
    assert focused == dict(plain, replay_focus="search_entry_event_half_v1")
    assert validate_config(focused) == focused
    assert validate_config(plain) == plain
    with pytest.raises(ValueError):
        validate_config(dict(focused, replay_focus="unsupported"))
    with pytest.raises(ValueError):
        experiment_config("mlp", physical_protocol="load_warning_7pct", focus_search_entry=True)


def test_unfocused_search_authority_checkpoint_still_has_no_training_grant():
    config = experiment_config("gru", physical_protocol="load_warning_7pct")
    with pytest.raises(ValueError, match="new dynamic training qualification"):
        verify_training_registration({}, {}, config=config, qualification_path=None, expected_digest=None)
