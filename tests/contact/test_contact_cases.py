from __future__ import annotations

from dataclasses import asdict
import json
import math

import numpy as np
import pytest

from tools.validation.run_contact_cases import (
    ContactCase,
    TERMINATIONS,
    all_cases,
    result_document,
    run_case,
)


def test_separated_pose_has_no_contacts():
    result = run_case(ContactCase.separated(), 0.0002, "sdf")
    assert result.max_contacts == 0


def test_aligned_quasistatic_insertion_reaches_depth():
    result = run_case(ContactCase.aligned(), 0.0002, "sdf")
    assert result.termination == "SUCCESS"
    assert result.final_depth_m >= 0.0039
    assert np.isfinite(result.peak_force_n)


@pytest.mark.parametrize(
    "case, axis, expected_sign",
    [
        (ContactCase.x_offset(+0.00010), "fx", -1),
        (ContactCase.x_offset(-0.00010), "fx", +1),
        (ContactCase.y_offset(+0.00010), "fy", -1),
        (ContactCase.y_offset(-0.00010), "fy", +1),
    ],
)
def test_offset_contact_force_opposes_offset(case, axis, expected_sign):
    result = run_case(case, 0.0002, "sdf")
    assert result.termination == "SUCCESS"
    assert np.sign(getattr(result.peak_signed_wrench, axis)) == expected_sign


@pytest.mark.parametrize(
    "positive, negative, torque_axis",
    [
        (ContactCase.roll(+math.radians(1.5)), ContactCase.roll(-math.radians(1.5)), "tx"),
        (ContactCase.pitch(+math.radians(1.5)), ContactCase.pitch(-math.radians(1.5)), "ty"),
    ],
)
def test_tilt_pairs_produce_opposite_repeatable_primary_torque(
    positive, negative, torque_axis
):
    first_positive = run_case(positive, 0.0002, "sdf")
    second_positive = run_case(positive, 0.0002, "sdf")
    negative_result = run_case(negative, 0.0002, "sdf")
    positive_torque = getattr(first_positive.peak_signed_wrench, torque_axis)
    negative_torque = getattr(negative_result.peak_signed_wrench, torque_axis)
    assert positive_torque * negative_torque < 0.0
    assert getattr(second_positive.peak_signed_wrench, torque_axis) == positive_torque


def test_sdf_and_polygon32_agree_on_primary_offset_direction():
    case = ContactCase.x_offset(+0.00010)
    sdf = run_case(case, 0.0002, "sdf")
    polygon = run_case(case, 0.0002, "polygon32")
    assert np.sign(sdf.peak_signed_wrench.fx) == -1
    assert np.sign(polygon.peak_signed_wrench.fx) == -1


def test_result_schema_is_serializable_and_every_number_is_finite():
    result = run_case(ContactCase.combined(), 0.0002, "sdf")
    payload = asdict(result)
    assert result.termination in TERMINATIONS
    assert set(payload) == {
        "case",
        "collision_mode",
        "termination",
        "final_depth_m",
        "peak_force_n",
        "peak_torque_nm",
        "peak_signed_wrench",
        "max_contacts",
        "total_contact_samples",
        "max_penetration_m",
        "timestep_s",
        "speed_m_s",
        "spatial_step_m",
        "steps",
        "solver",
        "runtime_s",
    }
    numbers = []
    for value in payload.values():
        if isinstance(value, (float, int)) and not isinstance(value, bool):
            numbers.append(value)
        elif isinstance(value, dict):
            numbers.extend(item for item in value.values() if isinstance(item, (float, int)))
    assert numbers and all(np.isfinite(numbers))
    json.dumps(payload, allow_nan=False)


def test_case_catalog_is_complete_unique_and_serializable():
    cases = all_cases()
    assert [case.name for case in cases] == [
        "separated",
        "aligned",
        "x_offset_pos_100um",
        "x_offset_neg_100um",
        "y_offset_pos_100um",
        "y_offset_neg_100um",
        "roll_pos_1.5deg",
        "roll_neg_1.5deg",
        "pitch_pos_1.5deg",
        "pitch_neg_1.5deg",
        "combined_a",
        "combined_b",
    ]
    json.dumps([asdict(case) for case in cases], allow_nan=False)


def test_result_document_has_deterministic_sorted_serialization():
    result = run_case(ContactCase.aligned(), 0.0002, "sdf")
    document = result_document([result])
    assert document["cases"][1] == {
        "name": "aligned",
        "x_offset_m": 0.0,
        "y_offset_m": 0.0,
        "roll_rad": 0.0,
        "pitch_rad": 0.0,
        "start_origin_z_m": -0.004,
        "target_depth_m": 0.004,
    }
    first = json.dumps(document, sort_keys=True, indent=2, allow_nan=False)
    second = json.dumps(result_document([result]), sort_keys=True, indent=2, allow_nan=False)
    assert first == second
    assert list(json.loads(first)) == sorted(json.loads(first))
