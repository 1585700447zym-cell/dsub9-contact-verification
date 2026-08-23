from __future__ import annotations

from dataclasses import asdict
import json
import math
from typing import get_args, get_type_hints

import mujoco
import numpy as np
import pytest

import tools.validation.run_contact_cases as contact_runner
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


@pytest.mark.parametrize(
    "case, torque_axis, expected_sign",
    [
        (ContactCase.roll(+math.radians(1.5)), "tx", -1),
        (ContactCase.roll(-math.radians(1.5)), "tx", +1),
        (ContactCase.pitch(+math.radians(1.5)), "ty", -1),
        (ContactCase.pitch(-math.radians(1.5)), "ty", +1),
    ],
)
def test_tilt_torque_has_absolute_task_frame_direction(case, torque_axis, expected_sign):
    result = run_case(case, 0.0002, "sdf")
    assert np.sign(getattr(result.peak_signed_wrench, torque_axis)) == expected_sign


def test_combined_rotation_is_pitch_matrix_times_roll_matrix():
    case = ContactCase.combined()
    quaternion = contact_runner._quaternion(case)
    actual = np.empty(9)
    mujoco.mju_quat2Mat(actual, quaternion)
    actual = actual.reshape(3, 3)

    cr, sr = math.cos(case.roll_rad), math.sin(case.roll_rad)
    cp, sp = math.cos(case.pitch_rad), math.sin(case.pitch_rad)
    roll = np.array(((1.0, 0.0, 0.0), (0.0, cr, -sr), (0.0, sr, cr)))
    pitch = np.array(((cp, 0.0, sp), (0.0, 1.0, 0.0), (-sp, 0.0, cp)))
    expected = pitch @ roll
    np.testing.assert_allclose(actual, expected, rtol=0.0, atol=2e-16)
    for basis in np.eye(3):
        np.testing.assert_allclose(actual @ basis, expected @ basis, rtol=0.0, atol=2e-16)


@pytest.mark.parametrize(
    "case, depth_m",
    [
        (ContactCase.roll(+math.radians(1.5)), 0.00063),
        (ContactCase.combined(), 0.00018),
    ],
)
def test_fixed_pose_male_world_wrench_matches_generalized_constraint_force(
    case, depth_m
):
    model = contact_runner._load_model("sdf", 0.0002)
    data = mujoco.MjData(model)
    male_body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "male")
    data.qpos[:7] = (
        case.x_offset_m,
        case.y_offset_m,
        case.start_origin_z_m + depth_m,
        *contact_runner._quaternion(case),
    )
    data.qvel[:] = 0.0
    data.qacc_warmstart[:] = 0.0
    mujoco.mj_forward(model, data)

    actual, _ = contact_runner._male_world_wrench(model, data, male_body)
    body_rotation = np.asarray(data.xmat[male_body]).reshape(3, 3)
    expected = np.concatenate(
        (data.qfrc_constraint[:3], body_rotation @ data.qfrc_constraint[3:6])
    )

    male_as_geom1 = 0
    independent = np.zeros(6)
    lever_moment_norm = 0.0
    for index in range(data.ncon):
        contact = data.contact[index]
        local = np.zeros(6)
        mujoco.mj_contactForce(model, data, index, local)
        contact_to_world = np.asarray(contact.frame).reshape(3, 3).T
        if int(model.geom_bodyid[contact.geom1]) == male_body:
            male_as_geom1 += 1
            sign = -1.0
        elif int(model.geom_bodyid[contact.geom2]) == male_body:
            sign = +1.0
        else:
            continue
        force_world = sign * (contact_to_world @ local[:3])
        contact_torque_world = sign * (contact_to_world @ local[3:])
        lever_moment = np.cross(
            np.asarray(contact.pos) - data.xpos[male_body], force_world
        )
        independent[:3] += force_world
        independent[3:] += contact_torque_world + lever_moment
        lever_moment_norm += np.linalg.norm(lever_moment)

    assert data.ncon > 0
    assert male_as_geom1 > 0
    assert lever_moment_norm > 0.0
    # Both values are assembled from the same solved double-precision constraints;
    # 1e-12 absolute tolerance is well below the smallest reported diagnostic torque.
    np.testing.assert_allclose(actual, independent, rtol=1e-10, atol=1e-12)
    np.testing.assert_allclose(independent, expected, rtol=1e-10, atol=1e-12)


@pytest.mark.parametrize("body_is_geom2, sign", [(True, +1.0), (False, -1.0)])
def test_per_contact_transform_preserves_nonzero_local_torque_and_body_sign(
    body_is_geom2, sign
):
    contact_frame = np.array(
        (
            (0.0, 1.0, 0.0),
            (-1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0),
        )
    )
    local_wrench = np.array((1.25, -2.5, 3.75, 0.4, -0.6, 0.8))
    contact_position = np.array((0.30, -0.20, 0.50))
    task_origin = np.array((-0.10, 0.10, 0.20))

    actual = contact_runner._contact_wrench_on_body_world(
        contact_frame,
        local_wrench,
        contact_position,
        task_origin,
        body_is_geom2=body_is_geom2,
    )

    force = sign * (contact_frame.T @ local_wrench[:3])
    local_torque = sign * (contact_frame.T @ local_wrench[3:])
    lever_moment = np.cross(contact_position - task_origin, force)
    expected = np.concatenate((force, local_torque + lever_moment))
    assert np.linalg.norm(local_torque) > 0.0
    assert not np.allclose(expected[3:], lever_moment)
    np.testing.assert_allclose(actual, expected, rtol=0.0, atol=1e-15)


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


def test_public_termination_schema_has_only_reachable_pose_sweep_outcomes():
    assert get_args(contact_runner.Termination) == (
        "SUCCESS",
        "EXCESS_PENETRATION",
        "NUMERICAL_ERROR",
    )
    assert TERMINATIONS == frozenset(get_args(contact_runner.Termination))
    assert get_type_hints(contact_runner.ContactResult)["termination"] is contact_runner.Termination
    document = result_document([run_case(ContactCase.separated(), 0.0002, "sdf")])
    assert document["terminations"] == list(get_args(contact_runner.Termination))


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


def test_repeated_runs_use_fresh_controlled_runtime_and_reproduce_physics(monkeypatch):
    ticks = iter((10.0, 11.25, 20.0, 22.5))
    clock_calls = []

    def controlled_clock():
        value = next(ticks)
        clock_calls.append(value)
        return value

    monkeypatch.setattr(contact_runner, "_clock", controlled_clock)
    case = ContactCase.separated()
    first_result = run_case(case, 0.0002, "sdf")
    second_result = run_case(case, 0.0002, "sdf")
    assert first_result is not second_result
    first_payload = asdict(first_result)
    second_payload = asdict(second_result)
    first_runtime = first_payload.pop("runtime_s")
    second_runtime = second_payload.pop("runtime_s")
    assert clock_calls == [10.0, 11.25, 20.0, 22.5]
    assert first_runtime == 1.25
    assert second_runtime == 2.5
    assert first_payload == second_payload

    document = result_document([first_result])
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
    second = json.dumps(result_document([first_result]), sort_keys=True, indent=2, allow_nan=False)
    assert first == second
    assert list(json.loads(first)) == sorted(json.loads(first))
