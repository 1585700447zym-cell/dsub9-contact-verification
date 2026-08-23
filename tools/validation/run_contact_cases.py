"""Run deterministic quasi-static contact checks on the reviewed D-sub9 models.

The male task origin starts at ``z=-0.004 m`` for insertion cases.  Reported
depth is the commanded world-Z displacement from that start, so
``male_origin_z = start_origin_z_m + final_depth_m``.  Poses are prescribed;
this is neither a force controller nor a free-dynamics integration.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import asdict, dataclass
import functools
import hashlib
import json
import math
import os
from pathlib import Path
import time
from typing import Iterable, Literal

import mujoco
import numpy as np


CollisionMode = Literal["sdf", "polygon32"]
Termination = Literal["SUCCESS", "EXCESS_PENETRATION", "NUMERICAL_ERROR"]

ROOT = Path(__file__).resolve().parents[2]
FORMAL_MODEL = ROOT / "models" / "dsub9_pair.xml"
FALLBACK_MODEL = ROOT / "build" / "dsub9_pair_polygon32.xml"
PLUGIN_RELATIVE_PATH = Path("build/dsub9_hole_sdf/Release/dsub9_hole_sdf.dll")
PLUGIN = ROOT / PLUGIN_RELATIVE_PATH

DEFAULT_TIMESTEP_S = 0.0002
DEFAULT_SPEED_M_S = 0.05
MAX_PENETRATION_M = 0.000030
TERMINATIONS = frozenset({"SUCCESS", "EXCESS_PENETRATION", "NUMERICAL_ERROR"})
_clock = time.perf_counter


@dataclass(frozen=True)
class Wrench:
    """Force and moment on the male, in world/task-aligned axes."""

    fx: float
    fy: float
    fz: float
    tx: float
    ty: float
    tz: float


@dataclass(frozen=True)
class ContactCase:
    """Serializable prescribed-pose case; distances are metres and angles radians."""

    name: str
    x_offset_m: float
    y_offset_m: float
    roll_rad: float
    pitch_rad: float
    start_origin_z_m: float
    target_depth_m: float

    @staticmethod
    def separated() -> "ContactCase":
        return ContactCase("separated", 0.0, 0.0, 0.0, 0.0, -0.005, 0.0)

    @staticmethod
    def aligned() -> "ContactCase":
        return ContactCase("aligned", 0.0, 0.0, 0.0, 0.0, -0.004, 0.004)

    @staticmethod
    def x_offset(offset_m: float) -> "ContactCase":
        return ContactCase(
            _signed_case_name("x_offset", offset_m, "um", 1e6),
            float(offset_m), 0.0, 0.0, 0.0, -0.004, 0.004,
        )

    @staticmethod
    def y_offset(offset_m: float) -> "ContactCase":
        return ContactCase(
            _signed_case_name("y_offset", offset_m, "um", 1e6),
            0.0, float(offset_m), 0.0, 0.0, -0.004, 0.004,
        )

    @staticmethod
    def roll(angle_rad: float) -> "ContactCase":
        return ContactCase(
            _signed_case_name("roll", angle_rad, "deg", 180.0 / math.pi),
            0.0, 0.0, float(angle_rad), 0.0, -0.004, 0.004,
        )

    @staticmethod
    def pitch(angle_rad: float) -> "ContactCase":
        return ContactCase(
            _signed_case_name("pitch", angle_rad, "deg", 180.0 / math.pi),
            0.0, 0.0, 0.0, float(angle_rad), -0.004, 0.004,
        )

    @staticmethod
    def combined() -> "ContactCase":
        return ContactCase(
            "combined_a", 0.000060, -0.000040,
            math.radians(1.5), math.radians(-1.5), -0.004, 0.004,
        )

    @staticmethod
    def combined_b() -> "ContactCase":
        return ContactCase(
            "combined_b", -0.000060, 0.000040,
            math.radians(-1.5), math.radians(1.5), -0.004, 0.004,
        )

    def __post_init__(self) -> None:
        values = (
            self.x_offset_m,
            self.y_offset_m,
            self.roll_rad,
            self.pitch_rad,
            self.start_origin_z_m,
            self.target_depth_m,
        )
        if not self.name or not all(math.isfinite(value) for value in values):
            raise ValueError("contact case name and parameters must be finite")
        if self.target_depth_m < 0.0:
            raise ValueError("target_depth_m must be non-negative")


@dataclass(frozen=True)
class ContactResult:
    case: str
    collision_mode: str
    termination: Termination
    final_depth_m: float
    peak_force_n: float
    peak_torque_nm: float
    peak_signed_wrench: Wrench
    max_contacts: int
    total_contact_samples: int
    max_penetration_m: float
    timestep_s: float
    speed_m_s: float
    spatial_step_m: float
    steps: int
    solver: str
    runtime_s: float


def _signed_case_name(prefix: str, value: float, unit: str, scale: float) -> str:
    if not math.isfinite(value) or value == 0.0:
        raise ValueError(f"{prefix} requires a finite non-zero value")
    magnitude = abs(value) * scale
    rounded = round(magnitude)
    label = str(int(rounded)) if math.isclose(magnitude, rounded, abs_tol=1e-10) else f"{magnitude:g}"
    return f"{prefix}_{'pos' if value > 0.0 else 'neg'}_{label}{unit}"


def all_cases() -> tuple[ContactCase, ...]:
    """Return the centralized formal validation matrix in deterministic order."""

    return (
        ContactCase.separated(),
        ContactCase.aligned(),
        ContactCase.x_offset(+0.00010),
        ContactCase.x_offset(-0.00010),
        ContactCase.y_offset(+0.00010),
        ContactCase.y_offset(-0.00010),
        ContactCase.roll(+math.radians(1.5)),
        ContactCase.roll(-math.radians(1.5)),
        ContactCase.pitch(+math.radians(1.5)),
        ContactCase.pitch(-math.radians(1.5)),
        ContactCase.combined(),
        ContactCase.combined_b(),
    )


@contextmanager
def _project_root_cwd():
    previous = Path.cwd()
    os.chdir(ROOT)
    try:
        yield
    finally:
        os.chdir(previous)


@functools.lru_cache(maxsize=1)
def _register_sdf_plugin() -> None:
    if not PLUGIN.is_file():
        raise FileNotFoundError(f"build Task 4 plugin first: {PLUGIN}")
    # MuJoCo 3.9 on Windows was verified with a project-root cwd and this ASCII
    # project-relative path.  Do not replace it with the Unicode absolute path.
    with _project_root_cwd():
        mujoco.mj_loadPluginLibrary(PLUGIN_RELATIVE_PATH.as_posix())


@functools.lru_cache(maxsize=4)
def _load_model(collision_mode: CollisionMode, timestep_s: float) -> mujoco.MjModel:
    if collision_mode == "sdf":
        _register_sdf_plugin()
        model_path = FORMAL_MODEL
    elif collision_mode == "polygon32":
        model_path = FALLBACK_MODEL
    else:
        raise ValueError("collision_mode must be 'sdf' or 'polygon32'")
    if not model_path.is_file():
        raise FileNotFoundError(model_path)
    with _project_root_cwd():
        model = mujoco.MjModel.from_xml_path(model_path.relative_to(ROOT).as_posix())
    model.opt.timestep = timestep_s
    return model


def _quaternion(case: ContactCase) -> np.ndarray:
    """Return wxyz for R=Ry(pitch)@Rx(roll): roll acts first on vectors."""

    cr, sr = math.cos(case.roll_rad / 2.0), math.sin(case.roll_rad / 2.0)
    cp, sp = math.cos(case.pitch_rad / 2.0), math.sin(case.pitch_rad / 2.0)
    return np.array((cp * cr, cp * sr, sp * cr, -sp * sr), dtype=float)


def _contact_wrench_on_body_world(
    contact_frame: np.ndarray,
    local_wrench: np.ndarray,
    contact_position_world: np.ndarray,
    task_origin_world: np.ndarray,
    *,
    body_is_geom2: bool,
) -> np.ndarray:
    """Transform one geom2 contact wrench, including its moment arm, onto a body."""

    contact_to_world = np.asarray(contact_frame, dtype=float).reshape(3, 3).T
    local = np.asarray(local_wrench, dtype=float)
    sign = 1.0 if body_is_geom2 else -1.0
    force_world = sign * (contact_to_world @ local[:3])
    local_torque_world = sign * (contact_to_world @ local[3:])
    lever_world = (
        np.asarray(contact_position_world, dtype=float)
        - np.asarray(task_origin_world, dtype=float)
    )
    return np.concatenate(
        (force_world, local_torque_world + np.cross(lever_world, force_world))
    )


def _male_world_wrench(
    model: mujoco.MjModel, data: mujoco.MjData, male_body: int
) -> tuple[np.ndarray, float]:
    """Aggregate contact wrench on male about its task origin in world axes."""

    total = np.zeros(6, dtype=float)
    max_penetration = 0.0
    task_origin_world = np.asarray(data.xpos[male_body], dtype=float)
    for index in range(data.ncon):
        contact = data.contact[index]
        local_wrench = np.zeros(6, dtype=float)
        mujoco.mj_contactForce(model, data, index, local_wrench)
        body1 = int(model.geom_bodyid[contact.geom1])
        body2 = int(model.geom_bodyid[contact.geom2])
        if body2 == male_body:
            body_is_geom2 = True
        elif body1 == male_body:
            body_is_geom2 = False
        else:
            continue
        total += _contact_wrench_on_body_world(
            contact.frame,
            local_wrench,
            contact.pos,
            task_origin_world,
            body_is_geom2=body_is_geom2,
        )
        max_penetration = max(max_penetration, max(0.0, -float(contact.dist)))
    return total, max_penetration


def _finite_state(data: mujoco.MjData, wrench: np.ndarray, penetration: float) -> bool:
    return bool(
        np.all(np.isfinite(data.qpos))
        and np.all(np.isfinite(data.qfrc_constraint))
        and np.all(np.isfinite(wrench))
        and math.isfinite(penetration)
        and all(math.isfinite(float(data.contact[index].dist)) for index in range(data.ncon))
    )


def run_case(
    case: ContactCase,
    timestep_s: float,
    collision_mode: CollisionMode,
) -> ContactResult:
    """Prescribe a deterministic +Z pose sweep and collect male contact wrench."""

    if not math.isfinite(timestep_s) or timestep_s <= 0.0:
        raise ValueError("timestep_s must be finite and positive")
    model = _load_model(collision_mode, float(timestep_s))
    data = mujoco.MjData(model)
    male_body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "male")
    if male_body < 0:
        raise RuntimeError("model has no male body")

    spatial_step_m = DEFAULT_SPEED_M_S * timestep_s
    requested_intervals = math.ceil(case.target_depth_m / spatial_step_m) if case.target_depth_m else 0
    max_steps = requested_intervals + 1
    peak_components = np.zeros(6, dtype=float)
    peak_force = 0.0
    peak_torque = 0.0
    max_contacts = 0
    total_contact_samples = 0
    max_penetration = 0.0
    final_depth = 0.0
    termination: Termination = "NUMERICAL_ERROR"
    executed_steps = 0
    quaternion = _quaternion(case)
    started = _clock()

    for step_index in range(max_steps):
        depth = min(step_index * spatial_step_m, case.target_depth_m)
        data.qpos[:7] = (
            case.x_offset_m,
            case.y_offset_m,
            case.start_origin_z_m + depth,
            *quaternion,
        )
        data.qvel[:] = 0.0
        data.qacc_warmstart[:] = 0.0
        try:
            mujoco.mj_forward(model, data)
            wrench, penetration = _male_world_wrench(model, data, male_body)
        except Exception:
            termination = "NUMERICAL_ERROR"
            executed_steps = step_index + 1
            final_depth = depth
            break
        executed_steps = step_index + 1
        final_depth = depth
        if not _finite_state(data, wrench, penetration):
            termination = "NUMERICAL_ERROR"
            break

        replace = np.abs(wrench) > np.abs(peak_components)
        peak_components[replace] = wrench[replace]
        peak_force = max(peak_force, float(np.linalg.norm(wrench[:3])))
        peak_torque = max(peak_torque, float(np.linalg.norm(wrench[3:])))
        max_contacts = max(max_contacts, int(data.ncon))
        total_contact_samples += int(data.ncon)
        max_penetration = max(max_penetration, penetration)

        if max_penetration > MAX_PENETRATION_M:
            termination = "EXCESS_PENETRATION"
            break
        if math.isclose(depth, case.target_depth_m, rel_tol=0.0, abs_tol=1e-15):
            termination = "SUCCESS"
            break

    runtime_s = _clock() - started
    result_values = np.concatenate(
        (peak_components, np.array((peak_force, peak_torque, max_penetration, final_depth, runtime_s)))
    )
    if not np.all(np.isfinite(result_values)):
        termination = "NUMERICAL_ERROR"
        peak_components = np.nan_to_num(peak_components, nan=0.0, posinf=0.0, neginf=0.0)
        peak_force = float(np.nan_to_num(peak_force, nan=0.0, posinf=0.0, neginf=0.0))
        peak_torque = float(np.nan_to_num(peak_torque, nan=0.0, posinf=0.0, neginf=0.0))
        max_penetration = float(np.nan_to_num(max_penetration, nan=0.0, posinf=0.0, neginf=0.0))
        final_depth = float(np.nan_to_num(final_depth, nan=0.0, posinf=0.0, neginf=0.0))
        runtime_s = float(np.nan_to_num(runtime_s, nan=0.0, posinf=0.0, neginf=0.0))

    solver_name = mujoco.mjtSolver(model.opt.solver).name.removeprefix("mjSOL_")
    return ContactResult(
        case=case.name,
        collision_mode=collision_mode,
        termination=termination,
        final_depth_m=float(final_depth),
        peak_force_n=float(peak_force),
        peak_torque_nm=float(peak_torque),
        peak_signed_wrench=Wrench(*map(float, peak_components)),
        max_contacts=max_contacts,
        total_contact_samples=total_contact_samples,
        max_penetration_m=float(max_penetration),
        timestep_s=float(timestep_s),
        speed_m_s=DEFAULT_SPEED_M_S,
        spatial_step_m=float(spatial_step_m),
        steps=executed_steps,
        solver=f"{solver_name}(iterations={model.opt.iterations})",
        runtime_s=float(runtime_s),
    )


def result_document(results: Iterable[ContactResult]) -> dict:
    result_list = list(results)
    return {
        "cases": [asdict(case) for case in all_cases()],
        "coordinate_convention": {
            "depth_equation": "male_origin_world_z_m = start_origin_z_m + final_depth_m",
            "insertion_axis": "+world/task Z",
            "wrench": "on male body, world/task-aligned axes, moment about male task origin",
        },
        "limits": {
            "force_calibration": "diagnostic numerical model only; real insertion force uncalibrated",
            "max_penetration_m": MAX_PENETRATION_M,
            "penetration_basis": "30 um is 40% of the 75 um nominal radial pin-hole clearance",
            "sweep": "prescribed quasi-static poses; no force controller and no free-dynamics integration",
            "timestep_note": "timestep sensitivity changes speed*timestep spatial discretization and solver timestep",
        },
        "mujoco_version": mujoco.mj_versionString(),
        "results": [asdict(result) for result in result_list],
        "schema_version": 2,
        "terminations": ["SUCCESS", "EXCESS_PENETRATION", "NUMERICAL_ERROR"],
    }


def _write_document(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _cli_results() -> list[ContactResult]:
    results = [run_case(case, DEFAULT_TIMESTEP_S, "sdf") for case in all_cases()]
    results.append(run_case(ContactCase.combined(), DEFAULT_TIMESTEP_S / 2.0, "sdf"))
    for case in (ContactCase.aligned(), ContactCase.x_offset(+0.00010), ContactCase.combined()):
        results.append(run_case(case, DEFAULT_TIMESTEP_S, "polygon32"))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="run the complete formal and comparison matrix")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.all:
        parser.error("--all is required")
    results = _cli_results()
    target = args.output if args.output.is_absolute() else ROOT / args.output
    _write_document(target, result_document(results))
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    print(f"wrote {len(results)} contact results to {target}")
    print(f"sha256={digest}")


if __name__ == "__main__":
    main()
