"""One-off scientific audit invoking unchanged, previously tested geometry inspectors.
Not a production API, training gate, dynamic rollout or parameter freeze.
Run from the repository root. Outputs are exclusive; copy this audit + its
bound protocol to a NEW directory for another attempt, never overwrite evidence.
"""
import hashlib
import json
import math
from pathlib import Path
import sys
import time

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
HERE = Path(__file__).resolve().parent
protocol = json.loads((HERE / "protocol.json").read_text(encoding="utf-8"))
for name, digest in protocol["evidence_sha256"].items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
source_protocol = json.loads((ROOT / protocol["source_protocol"]).read_text(encoding="utf-8"))
for name, digest in source_protocol["source_sha256"].items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == protocol["analysis_script_sha256"]
assert len(protocol["attempts"]) == 243
assert len({x["id"] for x in protocol["attempts"]}) == 243
from tools.learning.runtime import verify_runtime
runtime = verify_runtime(ROOT / "tmp/mujoco_3_13_probe")
from tools.dynamics.contact_candidate import candidate_environment
from tools.validation.run_contact_cases import ContactCase, _quaternion
from tools.validation.repair_contact_coverage import fast_witness, check_pose
from tools.validation.validate_contact_candidate import inspect
from tools.learning.guarded_environment import relative_rotation_rad

started = time.perf_counter()
rows = []
# Reserve output before native model construction; even interruption leaves a record.
with (HERE / "static_rows.jsonl").open("x", encoding="utf-8") as raw:
    env = candidate_environment(segments=256, timestep=.0002)
    metadata = env.metadata()
    assert metadata["segments"] == 256
    assert env.model.opt.ccd_tolerance == 1e-12
    for spec in protocol["attempts"]:
        row = {"spec": spec, "passed": False, "error": None}
        try:
            case = ContactCase(**spec["case"])
            witness = fast_witness(case, spec["depth_m"])
            coverage = check_pose(env.model, case, spec["depth_m"], witness)
            pose = [case.x_offset_m, case.y_offset_m, case.start_origin_z_m + spec["depth_m"], *_quaternion(case)]
            geometry = inspect(env.model, pose)
            expected = spec["expected_contact"]
            sentinel_ok = expected is None or bool(geometry["ncon"]) == expected
            if spec["id"] == "sentinel_wall_x":
                sentinel_ok = sentinel_ok and len(coverage["expected_pins"]) == 9
            row.update(witness=witness, coverage=coverage, geometry=geometry,
                actual_SO3_angle_deg=math.degrees(relative_rotation_rad([1,0,0,0], pose[3:])),
                passed=bool(coverage["status"] == "OK" and not coverage["missing_pins"]
                            and geometry["passed"] and sentinel_ok))
        except Exception as exc:
            row["error"] = repr(exc)
        raw.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
        raw.flush()
        rows.append(row)
        if len(rows) % 40 == 0:
            print(f"Recorded {len(rows)}/243 prescribed poses", flush=True)
unchanged = all(hashlib.sha256((ROOT / n).read_bytes()).hexdigest() == d
                for n,d in source_protocol["source_sha256"].items())
unchanged &= all(hashlib.sha256((ROOT / n).read_bytes()).hexdigest() == d
                 for n,d in protocol["evidence_sha256"].items())
summary = dict(static_sample_checks_passed=bool(unchanged and all(r["passed"] for r in rows)),
    source_unchanged=unchanged, attempts_planned=243, attempts_recorded=len(rows),
    passed_count=sum(r["passed"] for r in rows), failed_ids=[r["spec"]["id"] for r in rows if not r["passed"]],
    positive_witness_poses=sum(bool(r.get("coverage",{}).get("expected_pins")) for r in rows),
    positive_witness_pairs=sum(len(r.get("coverage",{}).get("expected_pins",[])) for r in rows),
    missing_pairs=sum(len(r.get("coverage",{}).get("missing_pins",[])) for r in rows),
    contact_poses=sum(bool(r.get("coverage",{}).get("contact_count")) for r in rows),
    warning_poses=sum(any(r.get("geometry",{}).get("warnings",[])) for r in rows),
    wall_seconds=time.perf_counter()-started, runtime=runtime, environment=metadata,
    parameter_frozen=False, model_scope_qualified=False, training_admitted=False,
    limitations=["prescribed static diagnostic poses, not dynamic states or admitted initializations",
                 "sampled positive witnesses for corresponding pin-hole pairs, not continuous clearance",
                 "finite/in-bounds axial contact depths do not qualify forces, stiffness or D-shell coverage",
                 "2.52deg diagnostic sample is NOT a new guard threshold, trust envelope or overshoot guarantee"])
with (HERE / "static_assessment.json").open("x", encoding="utf-8") as f:
    json.dump(summary,f,ensure_ascii=False,allow_nan=False,indent=2)
print(json.dumps({k:v for k,v in summary.items() if k not in ("runtime","environment")}, ensure_ascii=False), flush=True)
raise SystemExit(0 if summary["static_sample_checks_passed"] else 1)
