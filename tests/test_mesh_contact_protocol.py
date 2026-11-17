import pytest

from tools.learning.recovery_learning_contract import experiment_config, validate_config, verify_training_registration


def test_mesh_contact_runtime_uses_a_distinct_unqualified_domain():
    old = experiment_config("gru", physical_protocol="load_warning_7pct")
    fixed = experiment_config("gru", physical_protocol="load_warning_7pct_mesh_contact")
    physical = dict(fixed["physical_protocol"])
    runtime = physical.pop("collision_runtime_sha256")
    assert len(runtime) == 64 and set(runtime) <= set("0123456789abcdef")
    assert physical.pop("version") != old["physical_protocol"]["version"]
    assert physical == {key: value for key, value in old["physical_protocol"].items() if key != "version"}
    assert validate_config(fixed) == fixed
    with pytest.raises(ValueError, match="qualification"):
        verify_training_registration({}, {}, config=fixed, qualification_path=None, expected_digest=None)
    fixed["physical_protocol"]["collision_runtime_sha256"] = "0"*64
    with pytest.raises(ValueError):
        validate_config(fixed)


def test_mesh_contact_focus_replay_is_an_explicit_gru_training_configuration():
    plain = experiment_config("gru", physical_protocol="load_warning_7pct_mesh_contact")
    focused = experiment_config("gru", physical_protocol="load_warning_7pct_mesh_contact", focus_search_entry=True)
    assert focused == dict(plain, replay_focus="search_entry_event_half_v1")
    assert validate_config(focused) == focused
    with pytest.raises(ValueError, match="not registered"):
        verify_training_registration({}, {}, config=focused, qualification_path=None, expected_digest=None)
    with pytest.raises(ValueError):
        experiment_config("mlp", physical_protocol="load_warning_7pct_mesh_contact", focus_search_entry=True)
