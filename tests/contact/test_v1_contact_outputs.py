from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from tools.validation.run_contact_cases import (
    ContactResult,
    ContactSample,
    ContactTrace,
    Wrench,
    all_cases,
)
from tools.validation.run_v1_contact_validation import (
    build_trace_document,
    write_convergence_json,
    write_trace_csv,
    write_trace_json,
)
from tools.validation.v1_convergence import build_convergence_document


TIMESTEPS = (0.0004, 0.0002, 0.0001)


def _trace(case, timestep_s: float) -> ContactTrace:
    samples = (
        ContactSample(
            step_index=0,
            depth_m=0.0,
            male_origin_z_m=case.start_origin_z_m,
            wrench=Wrench(0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
            force_norm_n=0.0,
            torque_norm_nm=0.0,
            contact_count=0,
            penetration_m=0.0,
        ),
    )
    summary = ContactResult(
        case=case.name,
        collision_mode="sdf",
        contact_profile="uncalibrated_baseline_v1",
        termination="SUCCESS",
        final_depth_m=0.0,
        peak_force_n=0.0,
        peak_torque_nm=0.0,
        peak_signed_wrench=Wrench(0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        max_contacts=0,
        total_contact_samples=0,
        max_penetration_m=0.0,
        timestep_s=timestep_s,
        speed_m_s=0.00001 / timestep_s,
        spatial_step_m=0.00001,
        steps=1,
        solver="Newton(iterations=100)",
        runtime_s=9.876,
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


def _matrix() -> tuple[ContactTrace, ...]:
    return tuple(
        _trace(case, timestep_s)
        for case in all_cases()
        for timestep_s in TIMESTEPS
    )


def test_trace_document_has_frozen_schema_matrix_and_source_hash():
    document = build_trace_document(_matrix(), "a" * 64)

    assert document["schema_version"] == 1
    assert document["source_contact_results_sha256"] == "a" * 64
    assert document["timestep_values_s"] == [0.0004, 0.0002, 0.0001]
    assert document["spatial_step_m"] == 0.00001
    assert len(document["traces"]) == 36
    assert "runtime_s" not in document["traces"][0]["summary"]
    json.dumps(document, allow_nan=False)


def test_csv_is_utf8_bom_lf_and_has_flat_wrench_columns(tmp_path: Path):
    output = tmp_path / "trace.csv"

    write_trace_csv(_matrix(), output)

    raw = output.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" not in raw
    header = output.read_text(encoding="utf-8-sig").splitlines()[0]
    assert "fx_n" in header
    assert "tz_nm" in header
    assert "penetration_m" in header


def test_trace_document_rejects_incomplete_three_timestep_matrix():
    with pytest.raises(ValueError, match="incomplete timestep matrix"):
        build_trace_document(_matrix()[:-1], "b" * 64)


def test_trace_document_rejects_summary_that_does_not_end_at_last_sample():
    traces = list(_matrix())
    traces[0] = replace(
        traces[0],
        summary=replace(traces[0].summary, final_depth_m=0.00001),
    )

    with pytest.raises(ValueError, match="last sample"):
        build_trace_document(traces, "f" * 64)


def test_trace_json_rejects_unsupported_schema_without_overwriting(tmp_path: Path):
    output = tmp_path / "trace.json"
    output.write_text("original\n", encoding="utf-8")

    with pytest.raises(ValueError, match="schema_version"):
        write_trace_json({"schema_version": 2}, output)

    assert output.read_text(encoding="utf-8") == "original\n"


def test_trace_json_rejects_nan_without_overwriting(tmp_path: Path):
    output = tmp_path / "trace.json"
    output.write_text("original\n", encoding="utf-8")
    document = build_trace_document(_matrix(), "c" * 64)
    document["traces"][0]["samples"][0]["force_norm_n"] = float("nan")

    with pytest.raises(ValueError):
        write_trace_json(document, output)

    assert output.read_text(encoding="utf-8") == "original\n"


def test_convergence_writer_accepts_schema_one_and_rejects_other_schema(
    tmp_path: Path,
):
    output = tmp_path / "convergence.json"
    document = build_convergence_document(_matrix())

    write_convergence_json(document, output)
    assert json.loads(output.read_text(encoding="utf-8"))["schema_version"] == 1

    with pytest.raises(ValueError, match="schema_version"):
        write_convergence_json({"schema_version": 3}, output)


def test_csv_rejects_nonfinite_sample_without_replacing_existing_file(
    tmp_path: Path,
):
    output = tmp_path / "trace.csv"
    output.write_text("original\n", encoding="utf-8")
    traces = list(_matrix())
    bad_sample = replace(traces[0].samples[0], penetration_m=float("inf"))
    traces[0] = replace(traces[0], samples=(bad_sample,))

    with pytest.raises(ValueError, match="finite"):
        write_trace_csv(traces, output)

    assert output.read_text(encoding="utf-8") == "original\n"
