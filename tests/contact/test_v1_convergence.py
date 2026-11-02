from __future__ import annotations

from dataclasses import replace

import pytest

from tools.validation.run_contact_cases import (
    ContactCase,
    ContactResult,
    ContactSample,
    ContactTrace,
    Wrench,
)
from tools.validation.v1_convergence import (
    build_convergence_document,
    compare_trace,
    primary_component_for_case,
)


def _trace(
    timestep_s: float,
    values: tuple[float, ...] = (1.0, 2.0, 3.0),
    *,
    case: ContactCase | None = None,
    termination: str = "SUCCESS",
    final_depth_m: float = 0.00002,
    penetration_m: float = 0.000005,
) -> ContactTrace:
    case = case or ContactCase.x_offset(+0.00010)
    samples = tuple(
        ContactSample(
            step_index=index,
            depth_m=index * 0.00001,
            male_origin_z_m=case.start_origin_z_m + index * 0.00001,
            wrench=Wrench(value, 0.0, 0.0, 0.01 * value, 0.0, 0.0),
            force_norm_n=abs(value),
            torque_norm_nm=abs(0.01 * value),
            contact_count=0 if value == 0.0 else 1,
            penetration_m=0.0 if value == 0.0 else penetration_m,
        )
        for index, value in enumerate(values)
    )
    peak_value = max(values, key=abs)
    summary = ContactResult(
        case=case.name,
        collision_mode="sdf",
        contact_profile="uncalibrated_baseline_v1",
        termination=termination,
        final_depth_m=final_depth_m,
        peak_force_n=max(abs(value) for value in values),
        peak_torque_nm=max(abs(0.01 * value) for value in values),
        peak_signed_wrench=Wrench(
            peak_value, 0.0, 0.0, 0.01 * peak_value, 0.0, 0.0
        ),
        max_contacts=0 if not any(values) else 1,
        total_contact_samples=sum(value != 0.0 for value in values),
        max_penetration_m=0.0 if not any(values) else penetration_m,
        timestep_s=timestep_s,
        speed_m_s=0.00001 / timestep_s,
        spatial_step_m=0.00001,
        steps=len(samples),
        solver="Newton(iterations=100)",
        runtime_s=0.1,
    )
    return ContactTrace(
        case=case,
        collision_mode="sdf",
        contact_profile=summary.contact_profile,
        timestep_s=timestep_s,
        spatial_step_m=0.00001,
        solver=summary.solver,
        samples=samples,
        summary=summary,
    )


def test_identical_three_timestep_traces_have_zero_error_and_pass():
    document = build_convergence_document(
        (_trace(0.0001), _trace(0.0002), _trace(0.0004))
    )

    assert document["schema_version"] == 1
    assert document["overall_status"] == "PASS"
    medium = document["cases"][0]["comparisons"]["0.0002"]
    assert medium["peak_force_relative_error"] == 0.0
    assert medium["peak_torque_relative_error"] == 0.0
    assert medium["primary_component_normalized_rmse"] == 0.0


def test_zero_reference_uses_null_relative_metrics_and_absolute_gate():
    aligned = ContactCase.aligned()
    comparison = compare_trace(
        _trace(0.0001, (0.0, 0.0, 0.0), case=aligned),
        _trace(0.0002, (0.0, 0.0, 0.0), case=aligned),
    )

    assert comparison["peak_force_relative_error"] is None
    assert comparison["peak_torque_relative_error"] is None
    assert comparison["primary_component_normalized_rmse"] is None
    assert comparison["zero_contact_absolute_pass"] is True
    assert comparison["status"] == "PASS"


def test_medium_threshold_failure_keeps_measured_values():
    comparison = compare_trace(_trace(0.0001), _trace(0.0002, (1.3, 2.6, 3.9)))

    assert comparison["relative_limit"] == 0.10
    assert comparison["peak_force_relative_error"] == pytest.approx(0.30)
    assert comparison["primary_component_normalized_rmse"] == pytest.approx(
        (0.3**2 + 0.6**2 + 0.9**2) ** 0.5 / (3**0.5 * 3.0)
    )
    assert comparison["status"] == "FAIL"


@pytest.mark.parametrize(
    "candidate, failed_gate",
    [
        (_trace(0.0002, (-1.0, -2.0, -3.0)), "primary_sign_pass"),
        (_trace(0.0002, termination="EXCESS_PENETRATION"), "termination_match"),
        (_trace(0.0002, final_depth_m=0.00004), "termination_depth_pass"),
        (_trace(0.0002, termination="NUMERICAL_ERROR"), "no_numerical_error"),
    ],
)
def test_hard_gate_failures_are_explicit(candidate, failed_gate):
    comparison = compare_trace(_trace(0.0001), candidate)

    assert comparison[failed_gate] is False
    assert comparison["status"] == "FAIL"


def test_aligned_nonzero_load_fails_absolute_zero_contact_gate():
    aligned = ContactCase.aligned()
    comparison = compare_trace(
        _trace(0.0001, (0.0, 0.0, 0.0), case=aligned),
        _trace(0.0002, (0.0, 2e-12, 0.0), case=aligned),
    )

    assert comparison["zero_contact_absolute_pass"] is False
    assert comparison["status"] == "FAIL"


def test_one_spatial_step_termination_difference_passes_despite_float_roundoff():
    comparison = compare_trace(
        _trace(0.0001, final_depth_m=0.00390),
        _trace(0.0002, final_depth_m=0.00391),
    )

    assert comparison["termination_depth_delta_m"] == pytest.approx(0.00001)
    assert comparison["termination_depth_pass"] is True


@pytest.mark.parametrize(
    "case_name, expected",
    [
        ("x_offset_pos_100um", "fx"),
        ("y_offset_neg_100um", "fy"),
        ("roll_pos_1.5deg", "tx"),
        ("pitch_neg_1.5deg", "ty"),
        ("combined_a", "tx"),
        ("aligned", None),
        ("separated", None),
    ],
)
def test_case_family_selects_frozen_primary_component(case_name, expected):
    assert primary_component_for_case(case_name) == expected


def test_comparison_rejects_misaligned_spatial_grids():
    candidate = replace(_trace(0.0002), spatial_step_m=0.00002)

    with pytest.raises(ValueError, match="spatial_step_m"):
        compare_trace(_trace(0.0001), candidate)
