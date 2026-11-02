from __future__ import annotations

import json
import math
from pathlib import Path

from PIL import Image
import pytest

from tools.validation.run_contact_cases import (
    ContactResult,
    ContactSample,
    ContactTrace,
    Wrench,
    all_cases,
)
from tools.validation.run_v1_contact_validation import build_trace_document
from tools.validation.v1_convergence import build_convergence_document
from tools.visualization.plot_v1_contact_validation import (
    _zero_metric_note,
    generate_v1_charts,
    load_v1_documents,
)


EXPECTED = {
    "01_横向偏移接触力_深度曲线.png",
    "02_倾斜接触力矩_深度曲线.png",
    "03_联合偏差载荷_深度曲线.png",
    "04_穿透量与接触数_深度曲线.png",
    "05_时间步收敛对比.png",
}


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


def _trace(case, timestep_s: float) -> ContactTrace:
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


def _documents(tmp_path: Path) -> tuple[Path, Path]:
    traces = tuple(
        _trace(case, timestep_s)
        for case in all_cases()
        for timestep_s in (0.0004, 0.0002, 0.0001)
    )
    trace_document = build_trace_document(traces, "d" * 64)
    convergence_document = build_convergence_document(traces)
    trace_path = tmp_path / "traces.json"
    convergence_path = tmp_path / "convergence.json"
    trace_path.write_text(
        json.dumps(trace_document, allow_nan=False), encoding="utf-8"
    )
    convergence_path.write_text(
        json.dumps(convergence_document, allow_nan=False), encoding="utf-8"
    )
    return trace_path, convergence_path


def test_generate_v1_charts_writes_five_readable_annotated_pngs(tmp_path: Path):
    trace_path, convergence_path = _documents(tmp_path)

    outputs = generate_v1_charts(trace_path, convergence_path, tmp_path / "charts")

    assert {path.name for path in outputs} == EXPECTED
    for path in outputs:
        with Image.open(path) as image:
            assert image.width >= 1600
            assert image.height >= 900
            assert "未经实物标定" in image.info["Disclaimer"]


def test_loader_rejects_unsupported_schema_instead_of_guessing(tmp_path: Path):
    trace_path, convergence_path = _documents(tmp_path)
    document = json.loads(trace_path.read_text(encoding="utf-8"))
    document["schema_version"] = 2
    trace_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="schema-1"):
        load_v1_documents(trace_path, convergence_path)


def test_loader_rejects_missing_required_case(tmp_path: Path):
    trace_path, convergence_path = _documents(tmp_path)
    document = json.loads(trace_path.read_text(encoding="utf-8"))
    document["traces"] = [
        trace for trace in document["traces"] if trace["case"] != "combined_a"
    ]
    trace_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="combined_a"):
        load_v1_documents(trace_path, convergence_path)


def test_zero_height_convergence_bars_get_an_explicit_visual_note():
    assert _zero_metric_note([0.0, 0.0, 0.0]) == (
        "所有适用相对指标均为 0.00%，柱高为零"
    )
    assert _zero_metric_note([0.0, 0.01]) is None
