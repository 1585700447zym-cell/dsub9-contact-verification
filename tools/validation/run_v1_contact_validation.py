"""Generate the structured data for the D-sub9 V1 contact validation."""

from __future__ import annotations

from dataclasses import asdict
import csv
import hashlib
import io
import json
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


def generate_v1_data() -> tuple[dict, dict]:
    """Run the complete formal matrix and return trace plus convergence documents."""

    if not SOURCE_CONTACT_RESULTS.is_file():
        raise FileNotFoundError(SOURCE_CONTACT_RESULTS.resolve())
    source_sha256 = hashlib.sha256(SOURCE_CONTACT_RESULTS.read_bytes()).hexdigest()
    traces = tuple(
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
    return (
        build_trace_document(traces, source_sha256),
        build_convergence_document(traces),
    )

