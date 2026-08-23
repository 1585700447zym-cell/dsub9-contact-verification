from __future__ import annotations

from dataclasses import asdict
import math

import numpy as np

import tools.validation.run_contact_cases as contact_runner
from tools.model.generate_mjcf import baseline_contact_parameters
from tools.validation.run_contact_cases import ContactCase, result_document, run_case


def test_uncalibrated_profiles_perturb_friction_stiffness_and_damping():
    profiles = contact_runner.contact_parameter_profiles()
    assert tuple(profiles) == ("baseline", "low_response", "high_response")
    baseline = profiles["baseline"]
    low = profiles["low_response"]
    high = profiles["high_response"]

    assert baseline == baseline_contact_parameters()
    assert baseline.name == "uncalibrated_diagnostic_v1"
    assert low.name == "uncalibrated_low_response_v1"
    assert high.name == "uncalibrated_high_response_v1"
    assert low.friction[0] < baseline.friction[0] < high.friction[0]
    # A larger positive solref time constant is the softer direct-format setting.
    assert low.solref[0] > baseline.solref[0] > high.solref[0]
    assert low.solref[1] < baseline.solref[1] < high.solref[1]
    assert low.solimp != baseline.solimp != high.solimp
    assert {profile.margin_m for profile in profiles.values()} == {0.0}


def test_profile_is_part_of_model_cache_key_and_compiled_collision_arrays():
    profiles = contact_runner.contact_parameter_profiles()
    models = {
        key: contact_runner._load_model("sdf", 0.0002, key)
        for key in profiles
    }
    assert len({id(model) for model in models.values()}) == len(profiles)
    assert contact_runner._load_model("sdf", 0.0002, "low_response") is models["low_response"]

    for key, parameters in profiles.items():
        model = models[key]
        collision = np.flatnonzero(
            (np.asarray(model.geom_contype) != 0)
            | (np.asarray(model.geom_conaffinity) != 0)
        )
        visual = np.flatnonzero(
            (np.asarray(model.geom_contype) == 0)
            & (np.asarray(model.geom_conaffinity) == 0)
        )
        assert collision.size == 138
        np.testing.assert_allclose(
            model.geom_friction[collision],
            np.tile(parameters.friction, (collision.size, 1)),
        )
        np.testing.assert_allclose(
            model.geom_solref[collision],
            np.tile(parameters.solref, (collision.size, 1)),
        )
        np.testing.assert_allclose(
            model.geom_solimp[collision],
            np.tile(parameters.solimp, (collision.size, 1)),
        )
        np.testing.assert_allclose(model.geom_margin[collision], parameters.margin_m)
        # Profile application must not turn visual-only geoms into contact geoms.
        assert visual.size == 2


def test_low_and_high_profiles_preserve_qualitative_contact_conclusions():
    x_case = ContactCase.x_offset(+0.00010)
    combined_case = ContactCase.combined()
    profiles = ("baseline", "low_response", "high_response")
    x_results = [run_case(x_case, 0.0002, "sdf", profile=key) for key in profiles]
    combined_results = [
        run_case(combined_case, 0.0002, "sdf", profile=key) for key in profiles
    ]

    assert {result.termination for result in x_results} == {"SUCCESS"}
    assert {result.termination for result in combined_results} == {"EXCESS_PENETRATION"}
    assert all(result.peak_signed_wrench.fx < 0.0 for result in x_results)
    assert all(result.peak_signed_wrench.tx < 0.0 for result in combined_results)
    for result in (*x_results, *combined_results):
        payload = asdict(result)
        assert result.contact_profile.startswith("uncalibrated_")
        assert math.isfinite(result.peak_force_n)
        assert math.isfinite(result.peak_torque_nm)
        assert math.isfinite(result.max_penetration_m)
        assert result.peak_force_n >= 0.0
        assert result.peak_torque_nm >= 0.0
        assert result.max_penetration_m >= 0.0
        assert all(
            math.isfinite(value)
            for value in payload["peak_signed_wrench"].values()
        )


def test_result_document_records_profiles_and_diagnostic_sensitivity_scope():
    results = [
        run_case(ContactCase.combined(), 0.0002, "sdf", profile=key)
        for key in ("baseline", "low_response", "high_response")
    ]
    document = result_document(results)

    assert document["schema_version"] == 3
    assert tuple(document["contact_parameter_profiles"]) == (
        "baseline",
        "low_response",
        "high_response",
    )
    assert document["sensitivity"]["cases"] == [
        "x_offset_pos_100um",
        "combined_a",
    ]
    assert document["sensitivity"]["profiles"] == [
        "baseline",
        "low_response",
        "high_response",
    ]
    assert "not material calibration" in document["sensitivity"]["interpretation"]
    assert [result["contact_profile"] for result in document["results"]] == [
        "uncalibrated_diagnostic_v1",
        "uncalibrated_low_response_v1",
        "uncalibrated_high_response_v1",
    ]
