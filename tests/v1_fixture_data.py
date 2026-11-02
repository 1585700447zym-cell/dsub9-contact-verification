"""Complete, inexpensive schema-1 fixtures shared by V1 delivery tests."""

from __future__ import annotations

import json
import math
from pathlib import Path

from tools.reporting.generate_v1_contact_report import write_v1_report
from tools.validation.run_contact_cases import (
    ContactResult,
    ContactSample,
    ContactTrace,
    Wrench,
    all_cases,
)
from tools.validation.run_v1_contact_validation import (
    build_trace_document,
    write_trace_csv,
)
from tools.validation.v1_convergence import build_convergence_document
from tools.visualization.plot_v1_contact_validation import generate_v1_charts


def _wrench(case_name: str, magnitude: float) -> Wrench:
    sign = -1.0 if "pos" in case_name or case_name == "combined_a" else 1.0
    if case_name.startswith("x_offset_"):
        return Wrench(sign * magnitude, 0.0, 0.0, 0.0, 0.0, 0.0)
    if case_name.startswith("y_offset_"):
        return Wrench(0.0, sign * magnitude, 0.0, 0.0, 0.0, 0.0)
    if case_name.startswith("roll_"):
        return Wrench(0.0, 0.0, 0.0, sign * magnitude / 100.0, 0.0, 0.0)
    if case_name.startswith("pitch_"):
        return Wrench(0.0, 0.0, 0.0, 0.0, sign * magnitude / 100.0, 0.0)
    if case_name.startswith("combined_"):
        return Wrench(
            sign * magnitude,
            -sign * magnitude / 2.0,
            magnitude / 4.0,
            sign * magnitude / 100.0,
            0.0,
            0.0,
        )
    return Wrench(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)


def synthetic_trace(case, timestep_s: float) -> ContactTrace:
    samples = []
    for index, magnitude in enumerate((0.0, 1.0, 2.0)):
        wrench = _wrench(case.name, magnitude)
        samples.append(
            ContactSample(
                step_index=index,
                depth_m=index * 0.00001,
                male_origin_z_m=case.start_origin_z_m + index * 0.00001,
                wrench=wrench,
                force_norm_n=math.sqrt(wrench.fx**2 + wrench.fy**2 + wrench.fz**2),
                torque_norm_nm=math.sqrt(wrench.tx**2 + wrench.ty**2 + wrench.tz**2),
                contact_count=0 if magnitude == 0.0 else 2,
                penetration_m=index * 0.000001,
            )
        )
    peak = samples[-1]
    summary = ContactResult(
        case=case.name,
        collision_mode="sdf",
        contact_profile="uncalibrated_diagnostic_v1",
        termination="SUCCESS",
        final_depth_m=0.00002,
        peak_force_n=peak.force_norm_n,
        peak_torque_nm=peak.torque_norm_nm,
        peak_signed_wrench=peak.wrench,
        max_contacts=2 if peak.force_norm_n or peak.torque_norm_nm else 0,
        total_contact_samples=4 if peak.force_norm_n or peak.torque_norm_nm else 0,
        max_penetration_m=peak.penetration_m,
        timestep_s=timestep_s,
        speed_m_s=0.00001 / timestep_s,
        spatial_step_m=0.00001,
        steps=3,
        solver="Newton(iterations=100)",
        runtime_s=0.0,
    )
    return ContactTrace(
        case=case,
        collision_mode="sdf",
        contact_profile=summary.contact_profile,
        timestep_s=timestep_s,
        spatial_step_m=0.00001,
        solver=summary.solver,
        samples=tuple(samples),
        summary=summary,
    )


def synthetic_matrix() -> tuple[ContactTrace, ...]:
    return tuple(
        synthetic_trace(case, timestep_s)
        for case in all_cases()
        for timestep_s in (0.0004, 0.0002, 0.0001)
    )


def write_synthetic_documents(
    tmp_path: Path, source_sha256: str = "d" * 64
) -> tuple[Path, Path, dict, dict]:
    traces = synthetic_matrix()
    trace_document = build_trace_document(traces, source_sha256)
    convergence_document = build_convergence_document(traces)
    trace_path = tmp_path / "traces.json"
    convergence_path = tmp_path / "convergence.json"
    trace_path.write_text(
        json.dumps(trace_document, allow_nan=False), encoding="utf-8"
    )
    convergence_path.write_text(
        json.dumps(convergence_document, allow_nan=False), encoding="utf-8"
    )
    return trace_path, convergence_path, trace_document, convergence_document


def write_synthetic_delivery(
    tmp_path: Path, source_sha256: str = "d" * 64
) -> dict[str, Path]:
    trace_path, convergence_path, trace_document, convergence_document = (
        write_synthetic_documents(tmp_path, source_sha256)
    )
    csv_path = tmp_path / "traces.csv"
    chart_dir = tmp_path / "charts"
    report_path = tmp_path / "report.md"
    write_trace_csv(synthetic_matrix(), csv_path)
    generate_v1_charts(trace_path, convergence_path, chart_dir)
    write_v1_report(trace_document, convergence_document, report_path)
    return {
        "trace_json": trace_path,
        "trace_csv": csv_path,
        "convergence_json": convergence_path,
        "chart_dir": chart_dir,
        "report": report_path,
    }
