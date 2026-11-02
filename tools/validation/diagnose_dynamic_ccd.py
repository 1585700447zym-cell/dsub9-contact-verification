"""Frozen-pose CCD diagnosis, independent of the evolving dynamic controller.

Run from the project root with ``python -m tools.validation.diagnose_dynamic_ccd``.
Only the new diagnostic JSON is written. No model or historical result is edited.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import math
import platform
import time

import mujoco
import numpy as np

from tools.model import contact_development as modeldevelopment
from tools.validation.diagnose_v1_applicability import DEFAULT_HOLE, PINS, fingerprint
from tools.validation.repair_contact_coverage import check_pose, summarize
from tools.validation.run_contact_cases import ROOT, ContactCase


# Captured before rerunning the dynamic evidence matrix with a different backend.
# These literals keep this reproducer independent of subsequent baseline results.
FROZEN_QPOS = (
    9.829955011332662e-05, 2.0580398068480773e-07, -0.003749996726030722,
    0.9999999999929585, -4.878936777829016e-07,
    1.3155261512590427e-07, 3.71851351932903e-06,
)
ORIGINAL_FAILURE = {
    "source_file": "deliverables/dynamic_actuator_v1/n128_dt0.0002.json",
    "source_file_sha256_at_capture": "5a23ba837bd99f535fbf218cab028ff6b1448c6b30a62759dec8883f7f2b30f0",
    "case": "lateral_x",
    "segments": 128,
    "physics_timestep_s": 0.0002,
    "native_ccd": True,
    "ccd_iterations": 35,
    "ccd_tolerance": 1e-9,
    "stopping_started_s": 1.1999999999999005,
    "failure_time_s": 1.2555999999998944,
    "termination": "INVALID_PENETRATION",
    "reported_max_penetration_m": 0.0005398466783709657,
    "contact_count": 1112,
    "offending_pair": ["pin_05", "hole_convex128_05_main_013"],
    "peak_force_N": 0.03163371270463102,
    "peak_torque_about_G_Nm": 0.0013661202237460579,
    "previous_logged_pose": {
        "time_s": 1.2539999999998945,
        "position_m": [9.829951961514685e-05, 2.0576050566440848e-07, -0.0037499964543128627],
        "quaternion_wxyz": [0.999999999992955, -4.935135436192519e-07,
                            1.3547632417637288e-07, 3.7185993888222256e-06],
        "reported_max_penetration_m": 6.275616550228302e-09,
    },
}
OUTPUT = ROOT / "deliverables/dynamic_actuator_v1/ccd_diagnostic.json"
OLD_COVERAGE = ROOT / "deliverables/v1_applicability/diagnostic_results.json"


def quaternion_matrix(quaternion):
    """Direct unit-quaternion formula; no collision or MuJoCo transform calls."""
    w, x, y, z = np.asarray(quaternion) / np.linalg.norm(quaternion)
    return np.array([
        [1 - 2 * (y*y + z*z), 2 * (x*y - z*w), 2 * (x*z + y*w)],
        [2 * (x*y + z*w), 1 - 2 * (x*x + z*z), 2 * (y*z - x*w)],
        [2 * (x*z - y*w), 2 * (y*z + x*w), 1 - 2 * (x*x + y*y)],
    ])


def geometry_bounds():
    """Exact cylinder Z extrema and conservative whole-cylinder radial bounds."""
    matrix = quaternion_matrix(FROZEN_QPOS[3:])
    origin = np.asarray(FROZEN_QPOS[:3])
    rows = []
    for name, center, radius, half_length, hole_center in PINS:
        center_world = origin + matrix @ center
        z_extent = half_length * abs(matrix[2, 2]) + radius * math.hypot(matrix[2, 0], matrix[2, 1])
        highest_z = float(center_world[2] + z_extent)
        main_start_z = float(hole_center[2] + DEFAULT_HOLE.entry_depth)
        # Projection of a circular disk onto the XY plane never exceeds radius.
        radial_bound = float(np.linalg.norm(center_world[:2] - hole_center[:2])
                             + half_length * np.linalg.norm(matrix[:2, 2]) + radius)
        rows.append({
            "pin": name,
            "center_world_m": center_world.tolist(),
            "radius_m": radius,
            "half_length_m": half_length,
            "highest_world_z_m": highest_z,
            "lowest_world_z_m": float(center_world[2] - z_extent),
            "main_start_world_z_m": main_start_z,
            "main_axial_overlap_upper_bound_m": max(0.0, highest_z - main_start_z),
            "whole_cylinder_radial_upper_bound_m": radial_bound,
            "entry_inner_radius_m": DEFAULT_HOLE.entry_radius,
            "entry_radial_clearance_lower_bound_m": DEFAULT_HOLE.entry_radius - radial_bound,
            "entire_cylinder_inside_entry_radius": radial_bound < DEFAULT_HOLE.entry_radius,
        })
    return {
        "method": "Zmax = center_world_z + half_length*abs(Rzz) + radius*sqrt(Rzx^2+Rzy^2)",
        "radial_bound_method": "norm(center_xy-hole_xy) + half_length*norm(Rxy,z) + radius",
        "rotation_world_from_male": matrix.tolist(),
        "pins": rows,
        "max_main_axial_overlap_upper_bound_m": max(r["main_axial_overlap_upper_bound_m"] for r in rows),
        "all_cylinders_inside_entry_radius": all(r["entire_cylinder_inside_entry_radius"] for r in rows),
        "scope": "Independent bounds for the nine pin cylinders and their corresponding entry/main holes; not a D-shell or whole-assembly clearance certificate.",
    }


def option_record(model):
    return {"native_ccd": not bool(model.opt.disableflags & int(mujoco.mjtDisableBit.mjDSBL_NATIVECCD)),
            "disableflags": int(model.opt.disableflags),
            "ccd_iterations": int(model.opt.ccd_iterations),
            "ccd_tolerance": float(model.opt.ccd_tolerance)}


def inspect_frozen_pose(model):
    data = mujoco.MjData(model)
    data.qpos[:7] = FROZEN_QPOS
    # Deliberately reset velocity and warm start. Only the same geometry is queried.
    mujoco.mj_forward(model, data)
    contacts = []
    for contact in data.contact:
        contacts.append({
            "pair": [mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, int(g))
                     for g in (contact.geom1, contact.geom2)],
            "dist_m": float(contact.dist),
            "penetration_m": max(0.0, -float(contact.dist)),
            "position_world_m": np.asarray(contact.pos).tolist(),
            "normal_geom1_to_geom2_world": np.asarray(contact.frame[:3]).tolist(),
        })
    contacts.sort(key=lambda row: row["penetration_m"], reverse=True)
    return {"effective_options": option_record(model),
            "qpos_unchanged": bool(np.array_equal(data.qpos[:7], FROZEN_QPOS)),
            "time_s": float(data.time),
            "contact_count": int(data.ncon),
            "max_penetration_m": max((row["penetration_m"] for row in contacts), default=0.0),
            "deepest_contacts": contacts[:8],
            "finite": bool(np.isfinite(data.qacc).all() and np.isfinite(data.qfrc_constraint).all()
                           and all(np.isfinite(c.frame).all() and math.isfinite(c.dist) for c in data.contact)),
            "warning_counts": [int(w.number) for w in data.warning]}


def source_hashes():
    paths = ["tools/validation/diagnose_dynamic_ccd.py", "tools/model/contact_development.py",
             "tools/validation/repair_contact_coverage.py", "tools/validation/diagnose_v1_applicability.py",
             "tools/validation/run_contact_cases.py", OLD_COVERAGE.relative_to(ROOT).as_posix()]
    return {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in paths}


def main():
    old = json.loads(OLD_COVERAGE.read_text(encoding="utf-8"))
    before = fingerprint()
    inputs = source_hashes()
    if before != old["source_sha256"]:
        raise RuntimeError("Historical source hashes differ from the witness audit")
    model = modeldevelopment.load_model(128)
    original_disableflags = int(model.opt.disableflags)
    native_bit = int(mujoco.mjtDisableBit.mjDSBL_NATIVECCD)
    variants = []
    for iterations, tolerance in itertools.product((35, 100, 200), (1e-9, 1e-8, 1e-7, 1e-6)):
        model.opt.disableflags = original_disableflags & ~native_bit
        model.opt.ccd_iterations = iterations
        model.opt.ccd_tolerance = tolerance
        row = inspect_frozen_pose(model)
        variants.append(row)
        print("native", iterations, tolerance, row["max_penetration_m"], flush=True)
    model.opt.disableflags = original_disableflags | native_bit
    model.opt.ccd_iterations = 35
    model.opt.ccd_tolerance = 1e-9
    legacy = inspect_frozen_pose(model)
    variants.append(legacy)
    print("legacy_MPR", legacy["max_penetration_m"], flush=True)

    start = time.perf_counter()
    rows = [check_pose(model, ContactCase(**item["case"]), item["depth_m"], item["geometry_witness"])
            for item in old["coverage_audit"]]
    coverage = {"source": OLD_COVERAGE.relative_to(ROOT).as_posix(),
                "witness_sampling": {"angular_samples": 180, "axial_samples": 81, "cap_radial_samples": 33},
                "reporting_overlap_threshold_m": 1e-6,
                "effective_options": option_record(model),
                "wall_seconds_140_pose_checks": time.perf_counter() - start,
                "summary": summarize(rows), "rows": rows,
                "scope": "Reuses original high-density positive overlap witnesses; no missing witnesses is not an absence-of-collision proof."}
    bounds = geometry_bounds()
    native_baseline = variants[0]
    bound = bounds["max_main_axial_overlap_upper_bound_m"]
    native_inconsistent = (bounds["all_cylinders_inside_entry_radius"]
                           and native_baseline["max_penetration_m"] > bound + 1e-6)
    offending_bound = next(row["main_axial_overlap_upper_bound_m"] for row in bounds["pins"]
                           if row["pin"] == ORIGINAL_FAILURE["offending_pair"][0])
    legacy_bounded = legacy["max_penetration_m"] <= bound + 1e-9
    conclusion = (
        "Same-geometry frozen-pose evidence identifies an inconsistent native CCD penetration report, not a geometric model change. MPR resolves this fixture and is checked against the historical positive witnesses; this does not establish global backend accuracy."
        if native_inconsistent and legacy_bounded and coverage["summary"]["gate_pass"]
        else "The recorded numerical anomaly and/or MPR coverage result was not reproduced completely; inspect the raw comparison and coverage rows before drawing a backend conclusion."
    )
    previous = ORIGINAL_FAILURE["previous_logged_pose"]
    position_change = float(np.linalg.norm(np.asarray(FROZEN_QPOS[:3]) - previous["position_m"]))
    historical_unchanged = before == fingerprint()
    inputs_unchanged = inputs == source_hashes()
    if not historical_unchanged or not inputs_unchanged:
        raise RuntimeError("Read-only diagnostic inputs changed during the run")
    result = {
        "schema_version": 1,
        "scope": "Frozen-pose backend diagnosis and historical positive-witness coverage replay; no dynamic or physical validity claim.",
        "python_version": platform.python_version(), "mujoco_version": mujoco.__version__,
        "frozen_qpos": list(FROZEN_QPOS), "original_dynamic_failure": ORIGINAL_FAILURE,
        "previous_logged_to_failed_position_change_m": position_change,
        "all_variants_share_one_compiled_model_geometry": True,
        "historical_sources_unchanged": historical_unchanged,
        "historical_source_sha256": before, "diagnostic_input_sha256": inputs,
        "frozen_pose_comparisons": variants, "independent_geometry_bounds": bounds,
        "legacy_mpr_historical_coverage": coverage,
        "interpretation": {
            "native_baseline_exceeds_pin_main_overlap_upper_bound": native_inconsistent,
            "native_baseline_to_geometric_bound_ratio": native_baseline["max_penetration_m"] / bound if bound else None,
            "original_offending_pin_main_overlap_upper_bound_m": offending_bound,
            "legacy_mpr_max_penetration_m": legacy["max_penetration_m"],
            "legacy_mpr_respects_geometric_upper_bound_with_1nm_tolerance": legacy_bounded,
            "conclusion": conclusion,
        },
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                      encoding="utf-8", newline="\n")
    print(json.dumps({"bounds_m": bound, "coverage": coverage["summary"],
                      "native_inconsistent": native_inconsistent, "output": str(OUTPUT)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
