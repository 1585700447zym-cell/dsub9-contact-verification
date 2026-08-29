"""Generate the structured data for the D-sub9 V1 contact validation."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import tempfile
from typing import Iterable

import mujoco

from tools.validation.run_contact_cases import (
    ROOT,
    ContactTrace,
    all_cases,
    run_case_trace,
)
from tools.validation.v1_convergence import build_convergence_document


TIMESTEP_VALUES_S = (0.0004, 0.0002, 0.0001)
SPATIAL_STEP_M = 0.00001
SOURCE_CONTACT_RESULTS = ROOT / "reports" / "contact_validation_results.json"
TRACE_JSON = ROOT / "reports" / "v1_contact_traces.json"
TRACE_CSV = ROOT / "reports" / "v1_contact_traces.csv"
CONVERGENCE_JSON = ROOT / "reports" / "v1_timestep_convergence.json"
REPORT_MD = ROOT / "reports" / "v1_contact_validation_report.md"
CHART_DIR = (
    ROOT
    / "deliverables"
    / "chinese_visual_package"
    / "charts"
    / "v1_contact_validation"
)

_CSV_COLUMNS = (
    "case",
    "collision_mode",
    "contact_profile",
    "timestep_s",
    "spatial_step_m",
    "solver",
    "termination",
    "step_index",
    "depth_m",
    "male_origin_z_m",
    "fx_n",
    "fy_n",
    "fz_n",
    "tx_nm",
    "ty_nm",
    "tz_nm",
    "force_norm_n",
    "torque_norm_nm",
    "contact_count",
    "penetration_m",
)


def _validate_trace_matrix(traces: Iterable[ContactTrace]) -> tuple[ContactTrace, ...]:
    trace_tuple = tuple(traces)
    expected_cases = [case.name for case in all_cases()]
    grouped: dict[str, set[float]] = {name: set() for name in expected_cases}
    for trace in trace_tuple:
        if trace.case.name not in grouped:
            raise ValueError(f"unexpected V1 contact case {trace.case.name!r}")
        if trace.timestep_s in grouped[trace.case.name]:
            raise ValueError(
                f"duplicate trace for {trace.case.name} at {trace.timestep_s} s"
            )
        grouped[trace.case.name].add(trace.timestep_s)
        if trace.collision_mode != "sdf":
            raise ValueError("V1 trace matrix requires collision_mode='sdf'")
        if trace.spatial_step_m != SPATIAL_STEP_M:
            raise ValueError(
                f"V1 trace spatial_step_m must be {SPATIAL_STEP_M}"
            )
        if not trace.samples:
            raise ValueError(f"trace {trace.case.name} contains no finite samples")
        expected_indices = list(range(len(trace.samples)))
        if [sample.step_index for sample in trace.samples] != expected_indices:
            raise ValueError(
                f"trace {trace.case.name} sample indices must be consecutive"
            )
        for left, right in zip(trace.samples, trace.samples[1:]):
            if not math.isclose(
                right.depth_m - left.depth_m,
                trace.spatial_step_m,
                rel_tol=0.0,
                abs_tol=1e-15,
            ):
                raise ValueError(
                    f"trace {trace.case.name} samples must follow the fixed depth grid"
                )
        if not math.isclose(
            trace.summary.final_depth_m,
            trace.samples[-1].depth_m,
            rel_tol=0.0,
            abs_tol=1e-15,
        ):
            raise ValueError(
                f"trace {trace.case.name} summary must end at the last sample"
            )
        if trace.summary.steps != len(trace.samples):
            raise ValueError(
                f"trace {trace.case.name} summary steps must match sample count"
            )
        try:
            json.dumps(asdict(trace), allow_nan=False)
        except ValueError as error:
            raise ValueError(
                f"trace {trace.case.name} must contain only finite numbers"
            ) from error
    required = set(TIMESTEP_VALUES_S)
    for case_name, available in grouped.items():
        if available != required:
            raise ValueError(
                f"incomplete timestep matrix for {case_name}: {sorted(available)}"
            )
    expected_count = len(expected_cases) * len(TIMESTEP_VALUES_S)
    if len(trace_tuple) != expected_count:
        raise ValueError(
            f"V1 trace matrix must contain {expected_count} traces"
        )
    return trace_tuple


def _summary_payload(trace: ContactTrace) -> dict:
    payload = asdict(trace.summary)
    payload.pop("runtime_s")
    return payload


def _trace_payload(trace: ContactTrace) -> dict:
    return {
        "case": trace.case.name,
        "collision_mode": trace.collision_mode,
        "contact_profile": trace.contact_profile,
        "samples": [asdict(sample) for sample in trace.samples],
        "solver": trace.solver,
        "spatial_step_m": trace.spatial_step_m,
        "summary": _summary_payload(trace),
        "timestep_s": trace.timestep_s,
    }


def build_trace_document(
    traces: Iterable[ContactTrace], source_sha256: str
) -> dict:
    """Build and validate the deterministic schema-1 V1 trace document."""

    trace_tuple = _validate_trace_matrix(traces)
    if not re.fullmatch(r"[0-9a-fA-F]{64}", source_sha256):
        raise ValueError("source_sha256 must contain exactly 64 hexadecimal digits")
    profiles = {trace.contact_profile for trace in trace_tuple}
    solvers = {trace.solver for trace in trace_tuple}
    if len(profiles) != 1:
        raise ValueError("V1 trace matrix must use one contact profile")
    if len(solvers) != 1:
        raise ValueError("V1 trace matrix must use one solver configuration")

    document = {
        "cases": [asdict(case) for case in all_cases()],
        "collision_mode": "sdf",
        "contact_profile": next(iter(profiles)),
        "coordinate_convention": {
            "depth_equation": (
                "male_origin_world_z_m = start_origin_z_m + depth_m"
            ),
            "insertion_axis": "+world/task Z",
            "wrench": (
                "on male body, world/task-aligned axes, moment about male task origin"
            ),
        },
        "limits": {
            "force_calibration": (
                "diagnostic numerical model only; real insertion force uncalibrated"
            ),
            "runtime_note": (
                "runtime_s is intentionally omitted because it is machine-dependent"
            ),
            "sweep": (
                "prescribed quasi-static poses; no force controller and no free-dynamics integration"
            ),
        },
        "mujoco_version": mujoco.mj_versionString(),
        "schema_version": 1,
        "solver": next(iter(solvers)),
        "source_contact_results_sha256": source_sha256.lower(),
        "spatial_step_m": SPATIAL_STEP_M,
        "terminations": [
            "SUCCESS",
            "EXCESS_PENETRATION",
            "NUMERICAL_ERROR",
        ],
        "timestep_values_s": list(TIMESTEP_VALUES_S),
        "trace_count": len(trace_tuple),
        "traces": [_trace_payload(trace) for trace in trace_tuple],
        "units": {
            "angle": "rad",
            "depth": "m",
            "force": "N",
            "penetration": "m",
            "time": "s",
            "torque": "N*m",
        },
    }
    json.dumps(document, allow_nan=False)
    return document


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as stream:
            temporary_path = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _json_bytes(document: dict) -> bytes:
    return (
        json.dumps(document, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")


def write_trace_json(document: dict, path: Path = TRACE_JSON) -> None:
    if document.get("schema_version") != 1:
        raise ValueError("trace schema_version must be 1")
    _atomic_write_bytes(path, _json_bytes(document))


def write_convergence_json(document: dict, path: Path = CONVERGENCE_JSON) -> None:
    if document.get("schema_version") != 1:
        raise ValueError("convergence schema_version must be 1")
    _atomic_write_bytes(path, _json_bytes(document))


def _csv_rows(traces: Iterable[ContactTrace]) -> list[dict]:
    trace_tuple = _validate_trace_matrix(traces)
    rows = []
    for trace in trace_tuple:
        for sample in trace.samples:
            rows.append(
                {
                    "case": trace.case.name,
                    "collision_mode": trace.collision_mode,
                    "contact_profile": trace.contact_profile,
                    "timestep_s": trace.timestep_s,
                    "spatial_step_m": trace.spatial_step_m,
                    "solver": trace.solver,
                    "termination": trace.summary.termination,
                    "step_index": sample.step_index,
                    "depth_m": sample.depth_m,
                    "male_origin_z_m": sample.male_origin_z_m,
                    "fx_n": sample.wrench.fx,
                    "fy_n": sample.wrench.fy,
                    "fz_n": sample.wrench.fz,
                    "tx_nm": sample.wrench.tx,
                    "ty_nm": sample.wrench.ty,
                    "tz_nm": sample.wrench.tz,
                    "force_norm_n": sample.force_norm_n,
                    "torque_norm_nm": sample.torque_norm_nm,
                    "contact_count": sample.contact_count,
                    "penetration_m": sample.penetration_m,
                }
            )
    return rows


def write_trace_csv(
    traces: Iterable[ContactTrace], path: Path = TRACE_CSV
) -> None:
    rows = _csv_rows(traces)
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream, fieldnames=_CSV_COLUMNS, lineterminator="\n", extrasaction="raise"
    )
    writer.writeheader()
    writer.writerows(rows)
    _atomic_write_bytes(path, stream.getvalue().encode("utf-8-sig"))


def run_v1_matrix() -> tuple[ContactTrace, ...]:
    """Run all 12 frozen cases at all three frozen timesteps."""

    return tuple(
        run_case_trace(
            case,
            timestep_s,
            "sdf",
            profile="baseline",
            spatial_step_m=SPATIAL_STEP_M,
        )
        for case in all_cases()
        for timestep_s in TIMESTEP_VALUES_S
    )


def _source_sha256() -> str:
    if not SOURCE_CONTACT_RESULTS.is_file():
        raise FileNotFoundError(SOURCE_CONTACT_RESULTS.resolve())
    return hashlib.sha256(SOURCE_CONTACT_RESULTS.read_bytes()).hexdigest()


def generate_v1_data() -> tuple[dict, dict]:
    """Run the complete formal matrix and return trace plus convergence documents."""

    traces = run_v1_matrix()
    return (
        build_trace_document(traces, _source_sha256()),
        build_convergence_document(traces),
    )


def _strict_json(path: Path) -> dict:
    def reject_constant(token: str):
        raise ValueError(f"JSON contains non-finite value {token}")

    try:
        document = json.loads(
            path.read_text(encoding="utf-8"), parse_constant=reject_constant
        )
    except FileNotFoundError:
        raise FileNotFoundError(path.resolve()) from None
    if not isinstance(document, dict):
        raise ValueError(f"JSON root must be an object: {path.resolve()}")
    return document


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve_output(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def validate_existing_outputs(
    trace_json: Path,
    trace_csv: Path,
    convergence_json: Path,
    chart_dir: Path,
    report: Path,
) -> dict:
    """Validate a complete tracked delivery without calling MuJoCo."""

    from PIL import Image

    from tools.visualization.plot_v1_contact_validation import (
        DISCLAIMER,
        EXPECTED_FILENAMES,
        load_v1_documents,
    )

    trace_document = _strict_json(trace_json)
    convergence_document = _strict_json(convergence_json)
    load_v1_documents(trace_json, convergence_json)
    if trace_document.get("trace_count") != 36:
        raise ValueError("trace schema-1 must contain 36 traces")
    traces = trace_document.get("traces")
    if not isinstance(traces, list) or len(traces) != 36:
        raise ValueError("trace schema-1 traces list must contain 36 items")
    source_hash = _source_sha256()
    if trace_document.get("source_contact_results_sha256") != source_hash:
        raise ValueError("stored source schema-3 SHA-256 does not match current file")
    if convergence_document.get("trace_count") != 36:
        raise ValueError("convergence schema-1 must cover 36 traces")
    status = convergence_document.get("overall_status")
    if status not in {"PASS", "FAIL"}:
        raise ValueError("convergence overall_status must be PASS or FAIL")

    sample_count = sum(len(trace["samples"]) for trace in traces)
    try:
        with trace_csv.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if tuple(reader.fieldnames or ()) != _CSV_COLUMNS:
                raise ValueError("trace CSV columns do not match schema-1")
            csv_row_count = sum(1 for _ in reader)
    except FileNotFoundError:
        raise FileNotFoundError(trace_csv.resolve()) from None
    if csv_row_count != sample_count:
        raise ValueError(
            f"trace CSV row count {csv_row_count} does not match {sample_count} samples"
        )

    chart_paths = [chart_dir / name for name in EXPECTED_FILENAMES]
    for path in chart_paths:
        if not path.is_file():
            raise FileNotFoundError(path.resolve())
        with Image.open(path) as image:
            if image.width < 1600 or image.height < 900:
                raise ValueError(f"chart resolution is too small: {path.resolve()}")
            if DISCLAIMER not in image.info.get("Disclaimer", ""):
                raise ValueError(f"chart is missing disclaimer metadata: {path.resolve()}")

    try:
        report_text = report.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise FileNotFoundError(report.resolve()) from None
    if source_hash not in report_text or f"**{status}**" not in report_text:
        raise ValueError("report does not match the source hash and acceptance status")
    return {
        "chart_paths": chart_paths,
        "convergence_document": convergence_document,
        "sample_count": sample_count,
        "source_sha256": source_hash,
        "status": status,
        "trace_count": len(traces),
        "trace_document": trace_document,
    }


def _print_summary(
    *,
    trace_json: Path,
    trace_csv: Path,
    convergence_json: Path,
    chart_dir: Path,
    report: Path,
    trace_count: int,
    sample_count: int,
    status: str,
    source_sha256: str,
) -> None:
    print(f"轨迹数量：{trace_count}")
    print(f"样本数量：{sample_count}")
    print(f"总体验收：{status}")
    print(f"schema-3 源文件 SHA-256：{source_sha256}")
    for label, path in (
        ("轨迹 JSON", trace_json),
        ("轨迹 CSV", trace_csv),
        ("收敛 JSON", convergence_json),
        ("技术报告", report),
    ):
        print(f"{label}：{path.resolve()}｜SHA-256={_sha256(path)}")
    print(f"图表目录：{chart_dir.resolve()}")
    for path in sorted(chart_dir.glob("*.png")):
        print(f"图表：{path.resolve()}｜SHA-256={_sha256(path)}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="一条命令生成或核对 D-sub9 V1 接触验证交付。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="只核对现有文件，不运行 MuJoCo，也不改写任何输出",
    )
    parser.add_argument("--trace-json", type=Path, default=TRACE_JSON, help="轨迹 JSON")
    parser.add_argument("--trace-csv", type=Path, default=TRACE_CSV, help="轨迹 CSV")
    parser.add_argument(
        "--convergence-json",
        type=Path,
        default=CONVERGENCE_JSON,
        help="时间步收敛 JSON",
    )
    parser.add_argument("--chart-dir", type=Path, default=CHART_DIR, help="五张中文图表目录")
    parser.add_argument("--report", type=Path, default=REPORT_MD, help="V1 技术报告")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    trace_json = _resolve_output(args.trace_json)
    trace_csv = _resolve_output(args.trace_csv)
    convergence_json = _resolve_output(args.convergence_json)
    chart_dir = _resolve_output(args.chart_dir)
    report = _resolve_output(args.report)
    try:
        if args.check_only:
            checked = validate_existing_outputs(
                trace_json, trace_csv, convergence_json, chart_dir, report
            )
            _print_summary(
                trace_json=trace_json,
                trace_csv=trace_csv,
                convergence_json=convergence_json,
                chart_dir=chart_dir,
                report=report,
                trace_count=checked["trace_count"],
                sample_count=checked["sample_count"],
                status=checked["status"],
                source_sha256=checked["source_sha256"],
            )
            print("核对完成：没有重新运行 MuJoCo，也没有改写文件。")
            return 0

        from tools.reporting.generate_v1_contact_report import write_v1_report
        from tools.visualization.plot_v1_contact_validation import generate_v1_charts

        traces = run_v1_matrix()
        source_sha256 = _source_sha256()
        trace_document = build_trace_document(traces, source_sha256)
        convergence_document = build_convergence_document(traces)
        write_trace_json(trace_document, trace_json)
        write_trace_csv(traces, trace_csv)
        write_convergence_json(convergence_document, convergence_json)
        generate_v1_charts(trace_json, convergence_json, chart_dir)
        write_v1_report(trace_document, convergence_document, report)
        sample_count = sum(len(trace.samples) for trace in traces)
        _print_summary(
            trace_json=trace_json,
            trace_csv=trace_csv,
            convergence_json=convergence_json,
            chart_dir=chart_dir,
            report=report,
            trace_count=len(traces),
            sample_count=sample_count,
            status=convergence_document["overall_status"],
            source_sha256=source_sha256,
        )
        return 0
    except Exception as error:
        print(f"V1 接触验证失败：{error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
