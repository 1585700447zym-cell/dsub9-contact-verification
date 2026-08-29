from __future__ import annotations

from dataclasses import asdict
import math

import pytest

import tools.validation.run_contact_cases as contact_runner
from tools.validation.run_contact_cases import (
    DEFAULT_SPEED_M_S,
    ContactCase,
    ContactSample,
    ContactTrace,
    run_case,
    run_case_trace,
)


def test_trace_uses_monotonic_fixed_grid_and_summary_matches_samples():
    trace = run_case_trace(
        ContactCase.x_offset(+0.00010),
        0.0004,
        "sdf",
        spatial_step_m=0.00001,
    )

    depths = [sample.depth_m for sample in trace.samples]
    assert depths == sorted(depths)
    assert all(
        math.isclose(right - left, 0.00001, abs_tol=1e-15)
        for left, right in zip(depths, depths[1:])
    )
    assert trace.summary.final_depth_m == trace.samples[-1].depth_m
    assert trace.summary.steps == len(trace.samples)
    assert trace.timestep_s == 0.0004
    assert trace.spatial_step_m == 0.00001
    assert set(asdict(trace.samples[0])) == {
        "step_index",
        "depth_m",
        "male_origin_z_m",
        "wrench",
        "force_norm_n",
        "torque_norm_nm",
        "contact_count",
        "penetration_m",
    }


def test_explicit_trace_grid_common_prefix_is_independent_of_timestep():
    coarse = run_case_trace(
        ContactCase.combined(), 0.0004, "sdf", spatial_step_m=0.00001
    )
    fine = run_case_trace(
        ContactCase.combined(), 0.0001, "sdf", spatial_step_m=0.00001
    )

    common_count = min(len(coarse.samples), len(fine.samples))
    assert [sample.depth_m for sample in coarse.samples[:common_count]] == [
        sample.depth_m for sample in fine.samples[:common_count]
    ]
    assert abs(coarse.summary.final_depth_m - fine.summary.final_depth_m) <= 0.00001


@pytest.mark.parametrize("bad_step", [0.0, -1e-5, float("nan"), float("inf")])
def test_trace_rejects_nonpositive_or_nonfinite_spatial_step(bad_step):
    with pytest.raises(ValueError, match="spatial_step_m"):
        run_case_trace(
            ContactCase.aligned(), 0.0002, "sdf", spatial_step_m=bad_step
        )


def test_trace_summary_preserves_existing_run_case_behavior():
    case = ContactCase.x_offset(+0.00010)
    timestep_s = 0.0002
    expected = asdict(run_case(case, timestep_s, "sdf"))
    actual = asdict(
        run_case_trace(
            case,
            timestep_s,
            "sdf",
            spatial_step_m=DEFAULT_SPEED_M_S * timestep_s,
        ).summary
    )

    expected.pop("runtime_s")
    actual.pop("runtime_s")
    assert actual == expected


def test_numerical_error_trace_summary_stops_at_last_finite_sample(monkeypatch):
    original = contact_runner._male_world_wrench
    call_count = 0

    def fail_on_second_sample(model, data, male_body):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("controlled contact failure")
        return original(model, data, male_body)

    monkeypatch.setattr(
        contact_runner, "_male_world_wrench", fail_on_second_sample
    )
    trace = run_case_trace(
        ContactCase.aligned(), 0.0002, "sdf", spatial_step_m=0.00001
    )

    assert trace.summary.termination == "NUMERICAL_ERROR"
    assert len(trace.samples) == 1
    assert trace.summary.steps == len(trace.samples)
    assert trace.summary.final_depth_m == trace.samples[-1].depth_m
