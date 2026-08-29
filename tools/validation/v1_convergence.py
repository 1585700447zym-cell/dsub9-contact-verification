"""Evaluate fixed-depth-grid timestep convergence for V1 contact traces."""

from __future__ import annotations

from dataclasses import asdict
import math
from typing import Any, Iterable

from tools.validation.run_contact_cases import ContactTrace


REFERENCE_TIMESTEP_S = 0.0001
MEDIUM_TIMESTEP_S = 0.0002
COARSE_TIMESTEP_S = 0.0004
MEDIUM_RELATIVE_LIMIT = 0.10
COARSE_RELATIVE_LIMIT = 0.20
ZERO_CONTACT_ABS_LIMIT = 1e-12
DEPTH_DELTA_LIMIT_M = 0.00001

_TIMESTEP_LIMITS = {
    MEDIUM_TIMESTEP_S: MEDIUM_RELATIVE_LIMIT,
    COARSE_TIMESTEP_S: COARSE_RELATIVE_LIMIT,
}
_ZERO_CONTACT_CASES = frozenset({"separated", "aligned"})


def primary_component_for_case(case_name: str) -> str | None:
    """Return the frozen signed-wrench component used for a case family."""

    if case_name.startswith("x_offset_"):
        return "fx"
    if case_name.startswith("y_offset_"):
        return "fy"
    if case_name.startswith("roll_"):
        return "tx"
    if case_name.startswith("pitch_"):
        return "ty"
    if case_name.startswith("combined_"):
        return "tx"
    return None


def _all_finite(value: Any) -> bool:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return True
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    if isinstance(value, dict):
        return all(_all_finite(item) for item in value.values())
    if isinstance(value, (tuple, list)):
        return all(_all_finite(item) for item in value)
    return True


def _relative_error(reference: float, candidate: float) -> float | None:
    if reference == 0.0:
        return None
    return abs(candidate - reference) / abs(reference)


def _normalized_rmse(
    reference_values: list[float], candidate_values: list[float]
) -> float | None:
    scale = max((abs(value) for value in reference_values), default=0.0)
    if scale == 0.0:
        return None
    squared_error = sum(
        (candidate - reference) ** 2
        for reference, candidate in zip(reference_values, candidate_values)
    )
    return math.sqrt(squared_error / len(reference_values)) / scale


def _timestep_key(timestep_s: float) -> str:
    return f"{timestep_s:.4f}"


def compare_trace(reference: ContactTrace, candidate: ContactTrace) -> dict:
    """Compare one medium/coarse trace against the 0.0001 s reference."""

    if reference.case.name != candidate.case.name:
        raise ValueError("reference and candidate case names must match")
    if not math.isclose(
        reference.spatial_step_m,
        candidate.spatial_step_m,
        rel_tol=0.0,
        abs_tol=1e-15,
    ):
        raise ValueError("reference and candidate spatial_step_m must match")
    try:
        relative_limit = _TIMESTEP_LIMITS[candidate.timestep_s]
    except KeyError as error:
        raise ValueError(
            f"unsupported candidate timestep_s={candidate.timestep_s!r}"
        ) from error

    common_count = min(len(reference.samples), len(candidate.samples))
    if common_count == 0:
        raise ValueError("contact traces must contain at least one sample")
    reference_depths = [
        sample.depth_m for sample in reference.samples[:common_count]
    ]
    candidate_depths = [
        sample.depth_m for sample in candidate.samples[:common_count]
    ]
    if any(
        not math.isclose(left, right, rel_tol=0.0, abs_tol=1e-15)
        for left, right in zip(reference_depths, candidate_depths)
    ):
        raise ValueError("contact traces do not share the same depth grid")

    force_error = _relative_error(
        reference.summary.peak_force_n, candidate.summary.peak_force_n
    )
    torque_error = _relative_error(
        reference.summary.peak_torque_nm, candidate.summary.peak_torque_nm
    )
    primary_component = primary_component_for_case(reference.case.name)
    if primary_component is None:
        primary_rmse = None
        primary_sign_pass = True
    else:
        reference_values = [
            getattr(sample.wrench, primary_component)
            for sample in reference.samples[:common_count]
        ]
        candidate_values = [
            getattr(sample.wrench, primary_component)
            for sample in candidate.samples[:common_count]
        ]
        primary_rmse = _normalized_rmse(reference_values, candidate_values)
        reference_peak = getattr(
            reference.summary.peak_signed_wrench, primary_component
        )
        candidate_peak = getattr(
            candidate.summary.peak_signed_wrench, primary_component
        )
        primary_sign_pass = (
            reference_peak != 0.0
            and candidate_peak != 0.0
            and math.copysign(1.0, reference_peak)
            == math.copysign(1.0, candidate_peak)
        )

    finite_pass = _all_finite(asdict(reference)) and _all_finite(asdict(candidate))
    no_numerical_error = (
        reference.summary.termination != "NUMERICAL_ERROR"
        and candidate.summary.termination != "NUMERICAL_ERROR"
    )
    termination_match = (
        reference.summary.termination == candidate.summary.termination
    )
    termination_depth_delta_m = abs(
        candidate.summary.final_depth_m - reference.summary.final_depth_m
    )
    termination_depth_pass = (
        termination_depth_delta_m <= DEPTH_DELTA_LIMIT_M
        or math.isclose(
            termination_depth_delta_m,
            DEPTH_DELTA_LIMIT_M,
            rel_tol=0.0,
            abs_tol=1e-15,
        )
    )
    zero_contact_absolute_pass = True
    if reference.case.name in _ZERO_CONTACT_CASES:
        zero_contact_absolute_pass = max(
            reference.summary.peak_force_n,
            reference.summary.peak_torque_nm,
            candidate.summary.peak_force_n,
            candidate.summary.peak_torque_nm,
        ) <= ZERO_CONTACT_ABS_LIMIT

    metric_passes = {
        "peak_force_relative_pass": (
            force_error is None or force_error <= relative_limit
        ),
        "peak_torque_relative_pass": (
            torque_error is None or torque_error <= relative_limit
        ),
        "primary_component_rmse_pass": (
            primary_rmse is None or primary_rmse <= relative_limit
        ),
    }
    hard_passes = {
        "finite_pass": finite_pass,
        "no_numerical_error": no_numerical_error,
        "termination_match": termination_match,
        "primary_sign_pass": primary_sign_pass,
        "termination_depth_pass": termination_depth_pass,
        "zero_contact_absolute_pass": zero_contact_absolute_pass,
    }
    failed_checks = [
        name
        for name, passed in {**hard_passes, **metric_passes}.items()
        if not passed
    ]

    return {
        "candidate_timestep_s": candidate.timestep_s,
        "common_sample_count": common_count,
        "finite_pass": finite_pass,
        "max_penetration_delta_m": abs(
            candidate.summary.max_penetration_m
            - reference.summary.max_penetration_m
        ),
        "no_numerical_error": no_numerical_error,
        "peak_force_candidate_n": candidate.summary.peak_force_n,
        "peak_force_reference_n": reference.summary.peak_force_n,
        "peak_force_relative_error": force_error,
        "peak_force_relative_pass": metric_passes["peak_force_relative_pass"],
        "peak_torque_candidate_nm": candidate.summary.peak_torque_nm,
        "peak_torque_reference_nm": reference.summary.peak_torque_nm,
        "peak_torque_relative_error": torque_error,
        "peak_torque_relative_pass": metric_passes["peak_torque_relative_pass"],
        "primary_component": primary_component,
        "primary_component_normalized_rmse": primary_rmse,
        "primary_component_rmse_pass": metric_passes[
            "primary_component_rmse_pass"
        ],
        "primary_sign_pass": primary_sign_pass,
        "reference_timestep_s": reference.timestep_s,
        "relative_limit": relative_limit,
        "status": "PASS" if not failed_checks else "FAIL",
        "termination_candidate": candidate.summary.termination,
        "termination_depth_delta_m": termination_depth_delta_m,
        "termination_depth_pass": termination_depth_pass,
        "termination_match": termination_match,
        "termination_reference": reference.summary.termination,
        "zero_contact_absolute_limit": ZERO_CONTACT_ABS_LIMIT,
        "zero_contact_absolute_pass": zero_contact_absolute_pass,
        "failed_checks": failed_checks,
    }


def build_convergence_document(traces: Iterable[ContactTrace]) -> dict:
    """Build the schema-1 per-case and overall convergence decision document."""

    grouped: dict[str, dict[float, ContactTrace]] = {}
    case_order: list[str] = []
    for trace in traces:
        if trace.case.name not in grouped:
            grouped[trace.case.name] = {}
            case_order.append(trace.case.name)
        if trace.timestep_s in grouped[trace.case.name]:
            raise ValueError(
                f"duplicate trace for {trace.case.name} at {trace.timestep_s} s"
            )
        grouped[trace.case.name][trace.timestep_s] = trace
    if not grouped:
        raise ValueError("at least one complete three-timestep case is required")

    required = {REFERENCE_TIMESTEP_S, MEDIUM_TIMESTEP_S, COARSE_TIMESTEP_S}
    cases = []
    for case_name in case_order:
        available = set(grouped[case_name])
        if available != required:
            raise ValueError(
                f"incomplete timestep matrix for {case_name}: {sorted(available)}"
            )
        reference = grouped[case_name][REFERENCE_TIMESTEP_S]
        comparisons = {
            _timestep_key(timestep_s): compare_trace(
                reference, grouped[case_name][timestep_s]
            )
            for timestep_s in (MEDIUM_TIMESTEP_S, COARSE_TIMESTEP_S)
        }
        status = (
            "PASS"
            if all(item["status"] == "PASS" for item in comparisons.values())
            else "FAIL"
        )
        cases.append(
            {
                "case": case_name,
                "comparisons": comparisons,
                "primary_component": primary_component_for_case(case_name),
                "reference_final_depth_m": reference.summary.final_depth_m,
                "reference_max_penetration_m": reference.summary.max_penetration_m,
                "reference_peak_force_n": reference.summary.peak_force_n,
                "reference_peak_torque_nm": reference.summary.peak_torque_nm,
                "reference_termination": reference.summary.termination,
                "status": status,
            }
        )

    overall_status = (
        "PASS" if all(case["status"] == "PASS" for case in cases) else "FAIL"
    )
    return {
        "cases": cases,
        "limits": {
            "coarse_relative_limit": COARSE_RELATIVE_LIMIT,
            "depth_delta_limit_m": DEPTH_DELTA_LIMIT_M,
            "medium_relative_limit": MEDIUM_RELATIVE_LIMIT,
            "zero_contact_absolute_limit": ZERO_CONTACT_ABS_LIMIT,
        },
        "overall_status": overall_status,
        "reference_timestep_s": REFERENCE_TIMESTEP_S,
        "schema_version": 1,
        "trace_count": sum(len(items) for items in grouped.values()),
    }
