"""Read one saved G1 episode at a time. This module never constructs an environment."""
import argparse
from bisect import bisect_left, bisect_right
from collections import Counter
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from deliverables.learning_chain.noise50_yaw_repeat_postmortem_20261103.analysis_core import (
    euler_deg, pin_kinematics,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT = ROOT / "deliverables/learning_chain/g1_dynamic_900_20261105"
PERIOD = .002
NATIVE = .0002


class JsonStream:
    """Read arrays one element at a time, including the duplicate native ledgers."""
    def __init__(self, stream):
        self.stream = stream
        self.buf = ""
        self.i = 0
        self.decoder = json.JSONDecoder()

    def refill(self):
        chunk = self.stream.read(1 << 20)
        self.buf = self.buf[self.i:] + chunk
        self.i = 0
        return bool(chunk)

    def token(self):
        while True:
            while self.i < len(self.buf) and self.buf[self.i].isspace():
                self.i += 1
            if self.i < len(self.buf):
                return self.buf[self.i]
            if not self.refill():
                return ""

    def take(self, token):
        if self.token() != token:
            raise ValueError(f"Expected JSON delimiter {token}")
        self.i += 1

    def value(self):
        self.token()
        while True:
            try:
                value, end = self.decoder.raw_decode(self.buf, self.i)
            except json.JSONDecodeError:
                if self.refill():
                    continue
                raise
            if end < len(self.buf) and self.buf[end] not in " \t\r\n:,]}":
                if self.refill():
                    continue
                raise ValueError("Invalid JSON value")
            if end == len(self.buf) and self.refill():
                continue
            self.i = end
            return value

    def members(self, as_object=False):
        first, last = ("{", "}") if as_object else ("[", "]")
        self.take(first)
        if self.token() != last:
            while True:
                key = self.value() if as_object else None
                if as_object:
                    self.take(":")
                yield key
                if self.token() == last:
                    break
                self.take(",")
        self.take(last)

    def discard(self):
        if self.token() == "[":
            for _ in self.members():
                self.value()
        else:
            self.value()


def read_evidence(stream):
    keep = {"environment_events", "controller_events", "guard_facts", "interface_fault"}
    result = {}
    for key in stream.members(as_object=True):
        if key == "force_recovery":
            for _ in stream.members(as_object=True):
                stream.discard()
        elif key in keep:
            result[key] = stream.value()
        else:
            stream.discard()
    return result


def read_native(stream, collect):
    record = {}
    fields = ("time_s", "event_id", "force_N", "torque_G_Nm", "penetration_m",
              "linear_m_s", "angular_rad_s", "position_z_m")
    for key in stream.members(as_object=True):
        if key != "samples":
            record[key] = stream.value()
        elif collect:
            samples = []
            for _ in stream.members():
                item = stream.value()
                samples.append(tuple(item[name] for name in fields))
            record["samples"] = np.array(samples, dtype=float).reshape((-1, len(fields)))
        else:
            stream.discard()
    return record


def read_compact(path):
    compressed = path.suffix == ".gz"
    opener = gzip.open if compressed else open
    kept = {"case", "seed", "version", "episode_id", "policy_mode", "policy_source", "source_counts",
            "cumulative_peaks", "outcome", "cost", "error", "status", "stopped", "valid", "final_reason",
            "task_end_time_s", "stop_time_s", "audit_end_time_s", "archive_sha256", "finish_criteria",
            "dynamic_config", "model_xml_sha256", "reset_attempted", "reset_completed", "training_updates"}
    result = {}
    with opener(path, "rt", encoding="utf-8-sig") as file:
        s = JsonStream(file)
        for key in s.members(as_object=True):
            if key in kept:
                result[key] = s.value()
            elif key == "force_recovery":
                native = read_native(s, collect=compressed)
                if compressed:
                    result[key] = native
            elif key in ("evidence", "evidence_before_abort"):
                result[key] = read_evidence(s)
            elif key == "trace":
                cols = ("time_s", "position_m", "quaternion_wxyz", "phase", "policy_phase",
                        "velocity_world", "contact_wrench_M", "contact_wrench_G", "penetration_m")
                result[key] = [{k: f[k] for k in cols if k in f}
                               for _ in s.members() for f in [s.value()]]
            elif key == "transitions":
                phases = []
                for _ in s.members():
                    row = s.value()
                    phases.append((row["action_log"]["composition_inputs"]["phase"], row["action_active"]))
                result["executed"] = phases
            elif key == "source_cycles":
                result["source"] = [(f["phase"], f["enabled"]) for _ in s.members() for f in [s.value()]]
            else:
                s.discard()
        if s.token():
            raise ValueError("Unexpected trailing data")
    return result


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def describe_pose(frame, geometry):
    geom = geometry
    k = pin_kinematics(frame["position_m"], frame["quaternion_wxyz"],
                       geom._pin_centers, geom._pin_sizes, geom._holes[:, :2])
    rows = []
    for n, (size, hole) in enumerate(zip(geom._pin_sizes, geom._holes)):
        tip = k["tip_centers_m"][n] * 1e3
        err = k["tip_error_xy_m"][n] * 1e6
        row = dict(pin=n + 1, hole_x_mm=hole[0] * 1e3, hole_y_mm=hole[1] * 1e3,
                   tip_x_mm=tip[0], tip_y_mm=tip[1], tip_z_mm=tip[2],
                   tip_dx_um=err[0], tip_dy_um=err[1], tip_radial_offset_um=math.hypot(*err))
        for name, radius, lo, hi in geom._LAYERS:
            clearance = geom._layer_margin(k["centers_m"][n], k["rotation"], *size, lo, hi, hole[:2], radius)
            overlap = max(0., min(k["rim_hi_m"][n], hi) - max(k["rim_lo_m"][n], lo))
            row[f"{name}_margin_um"] = clearance * 1e6 if clearance is not None else None
            row[f"{name}_overlap_um"] = overlap * 1e6
            row[f"{name}_fit"] = bool(clearance is not None and clearance >= -geom.GEOMETRY_TOLERANCE_M)
        rows.append(row)
    clearances = [(r[f"{layer}_margin_um"], r["pin"], layer) for r in rows for layer in ("entry","main")
                  if r[f"{layer}_margin_um"] is not None]
    worst = min(clearances) if clearances else (None, None, None)
    main_fit = sum(r["main_fit"] for r in rows)
    fit = main_fit == 9 and worst[0] >= -geom.GEOMETRY_TOLERANCE_M * 1e6
    if fit != bool(geom.layered_pin_fit(frame)):
        raise ValueError("Per-pin and frozen referee verdicts differ")
    return dict(time_s=frame["time_s"], position_mm=[x * 1000 for x in frame["position_m"]],
                rpy_deg=euler_deg(k["rotation"]).tolist(), target_z_gap_mm=abs(frame["position_m"][2])*1000,
                force_N=float(np.linalg.norm(frame["contact_wrench_M"][:3])),
                deepest_pin_rim_mm=float(max(k["rim_hi_m"]))*1000, main_fit_count=main_fit,
                main_intersections=sum(r["main_margin_um"] is not None for r in rows), all_nine_fit=fit,
                present_worst_margin_um=worst[0], present_worst_pin=worst[1], present_worst_layer=worst[2],
                pins=rows)


def stable_window(samples, end, config):
    if end is None:
        return None
    selected = samples[(samples[:, 0] >= end-.1-1e-9) & (samples[:, 0] <= end+1e-9)]
    if not len(selected):
        return dict(samples=0, passed=False)
    times = selected[:, 0]
    peaks = selected[:, 2:7].max(axis=0)
    passes = (len(times) == 501 and abs(times[0]-(end-.1)) <= 1e-9 and abs(times[-1]-end) <= 1e-9
              and np.allclose(np.diff(times), NATIVE, atol=1e-9, rtol=0)
              and peaks[0] <= .5 and peaks[1] <= config["stop_torque_Nm"]
              and peaks[2] < config["stop_penetration_m"] and peaks[3] <= config["stopped_speed"]
              and peaks[4] <= config["stopped_angular_speed"])
    return dict(samples=len(times), duration_ms=(times[-1]-times[0])*1000, passed=bool(passes),
                max_force_N=peaks[0], max_torque_Nm=peaks[1], max_penetration_um=peaks[2]*1e6,
                max_linear_m_s=peaks[3], max_angular_rad_s=peaks[4])


def endpoint_z(samples, time):
    if time is None:
        return None
    matched = samples[np.abs(samples[:, 0]-time)<=1e-9]
    return float(matched[0, 7]) if len(matched) == 1 else None


def unload_facts(group, end, config):
    if end is not None:
        group = group[group[:, 0] <= end+1e-9]
    if not len(group):
        return {}
    tests = np.column_stack((group[:,2] <= .5, group[:,3] <= config["stop_torque_Nm"],
                             group[:,4] < config["stop_penetration_m"], group[:,5] <= config["stopped_speed"],
                             group[:,6] <= config["stopped_angular_speed"]))
    ok = tests.all(axis=1)
    breaks = np.flatnonzero(np.diff(np.r_[False,ok,False].astype(np.int8)))
    durations = group[breaks[1::2]-1,0] - group[breaks[::2],0]
    return dict(last_force_N=group[-1,2], min_force_N=float(min(group[:,2])),
                longest_stable_ms=1000*max(durations, default=0.),
                end_blockers=[n for n,valid in zip(("force","torque","penetration","linear_speed","angular_speed"),
                                                     tests[-1]) if not valid])


def describe_force(event, samples, receipt, trace, times, executed, source, evidence, next_trigger):
    start = event["trigger_time_s"]
    end = event["end_time_s"]
    group = samples[(samples[:,1] == event["id"]) & (samples[:,0] >= start-1e-9)]
    if end is not None:
        group = group[group[:,0] <= end+1e-9]
    retract, reached, resume = (event.get(k) for k in ("retract_start_time_s", "retracted_time_s", "resume_time_s"))
    z0, z1, z2 = (endpoint_z(group, tm) for tm in (retract, reached, resume))
    moving = group[group[:, 0] >= retract-1e-9] if retract is not None else []
    actual_max = float((z0-min(moving[:,7]))*1e6) if z0 is not None and len(moving) else None
    actual_at_reached = (z0-z1)*1e6 if z0 is not None and z1 is not None else None
    actual_at_resume = (z0-z2)*1e6 if z0 is not None and z2 is not None else None
    env = evidence["environment_events"]
    post = None
    if resume is not None and any(e["reason"]=="B2_RECOVERY_RESUMED" and e["phase"]=="RUNNING"
                                  and abs(e["time_s"]-resume)<1e-9 for e in env):
        following_stops = [e["time_s"] for e in env if e["time_s"] >= resume+1e-9 and e["phase"]!="RUNNING"]
        limit = min([times[-1], next_trigger, *following_stops])
        for i in range(bisect_left(times,resume-1e-9),len(executed)):
            if times[i] >= limit-1e-9:
                break
            if (executed[i] == ("SEARCH",True) and source[i] == ("SEARCH",True)
                    and trace[i+1]["phase"] == "RUNNING" and times[i+1] <= limit+1e-9):
                post = dict(cycle=i, start_s=times[i], end_s=times[i+1])
                break
    unload_tail = stable_window(group, event.get("unloaded_time_s"), receipt["dynamic_config"])
    resume_tail = stable_window(group, resume, receipt["dynamic_config"])
    reached_ok = actual_at_reached is not None and actual_at_reached >= 250.-1e-6
    resume_ok = actual_at_resume is not None and actual_at_resume >= 250.-1e-6
    attempted = end if event.get("status_reason") == "RECOVERY_RESUME_REJECTED" else resume
    attempt_z = endpoint_z(group, attempted)
    attempt_distance = (z0-attempt_z)*1e6 if z0 is not None and attempt_z is not None else None
    i = min(max(0, bisect_left(times,start-1e-9)-1),len(executed)-1)
    return dict(id=event["id"], status=event["status"], reason=event.get("status_reason"), eligible=event["eligible"],
                trigger_time_s=start, trigger_force_N=group[0,2] if len(group) else None,
                trigger_command_phase=executed[i][0] if executed else None, trigger_position_m=event.get("trigger_position_m"),
                event_peak_N=float(max(group[:,2])) if len(group) else None,
                unload_at_s=event.get("unloaded_time_s"), retract_at_s=retract, reached_at_s=reached,
                resume_at_s=resume, ended_at_s=end, peak_above_5_duration_ms=event["continuous_over_force_s"]*1e3,
                actual_retraction_at_distance_um=actual_at_reached, actual_retraction_at_resume_um=actual_at_resume,
                restart_attempt_time_s=attempted, actual_retraction_at_restart_attempt_um=attempt_distance,
                restart_shortfall_nm=None if attempt_distance is None else (250.-attempt_distance)*1000,
                stable_at_restart_attempt=stable_window(group, attempted, receipt["dynamic_config"]),
                unload_conditions=unload_facts(group, retract, receipt["dynamic_config"]),
                max_retraction_after_start_um=actual_max, unloading_stable=unload_tail,
                resume_stable=resume_tail, resumed_search_cycle=post,
                physical_chain_complete=bool(event["status"]=="COMPLETED" and unload_tail and unload_tail["passed"]
                    and reached_ok and resume_ok and resume_tail and resume_tail["passed"] and post))


def review(folder, geom):
    receipt = read_compact(folder/"receipt.json")
    path = folder/"episode.json.gz"
    batch = folder.parent.parent
    original_path = folder/"audit.json"
    reaudit_path = batch/"continuation"/(folder.name+".reaudit.json")
    original = json.loads(original_path.read_bytes()) if original_path.is_file() else {}
    audit_path = reaudit_path if reaudit_path.is_file() else original_path
    audit = json.loads(audit_path.read_bytes()) if audit_path.is_file() else {}
    previous_log = batch/"monitor"/(folder.name+".audit.log")
    continued_log = batch/"continuation"/(folder.name+".audit.log")
    earlier_error = None
    if not original and previous_log.is_file():
        lines = previous_log.read_text(encoding="utf-8", errors="replace").splitlines()
        earlier_error = next((s.strip() for s in reversed(lines) if "Error:" in s),None)
    latest_error = earlier_error
    if not audit and continued_log.is_file():
        lines = continued_log.read_text(encoding="utf-8", errors="replace").splitlines()
        latest_error = next((s.strip() for s in reversed(lines) if "Error:" in s),latest_error)
    row = dict(episode_id=folder.name, case=receipt["case"], receipt_status=receipt["status"],
               reason=receipt.get("final_reason") or receipt.get("error"), outcome=receipt.get("outcome"),
               reset_attempted=receipt.get("reset_attempted"), reset_completed=receipt.get("reset_completed"),
               audit_verified=audit.get("verified") is True,
               audit_evidence=audit_path.relative_to(batch).as_posix() if audit_path.is_file() else None,
               original_audit_verified=original.get("verified") is True,
               prior_audit_error=earlier_error, final_audit_error=None if audit else latest_error)
    if not path.is_file():
        return row
    h = sha(path)
    if h != receipt["archive_sha256"] or (audit.get("verified") and h != audit["archive_sha256"]):
        raise ValueError(f"{folder.name}: stored archive digest differs")
    if sha(folder/"model_used.xml") != receipt["model_xml_sha256"]:
        raise ValueError(f"{folder.name}: model XML digest differs")
    raw = read_compact(path)
    trace = raw["trace"]
    times = [f["time_s"] for f in trace]
    evidence = raw["evidence"]
    executed, source = raw["executed"], raw["source"]
    phases = Counter(phase for phase, active in executed if active)
    row.update(archive_sha256=h, native_peaks=raw.get("cumulative_peaks"),
               controller_events=evidence.get("controller_events"), environment_events=evidence.get("environment_events"),
               active_phase_cycles=dict(phases), source_mode=raw["policy_mode"], behavior=raw["policy_source"],
               force_events=[], fatal_reasons=raw.get("force_recovery",{}).get("fatal_reasons",[]),
               guard_facts=evidence.get("guard_facts"), counts=raw.get("source_counts"), frames={})
    if not trace:
        return row
    rotation_stop = next((e for e in evidence["environment_events"]
                          if "ROTATION_LIMIT" in e["reason"].split("+")), None)
    if rotation_stop:
        tm = rotation_stop["time_s"]
        after = min(len(times)-1,bisect_left(times,tm-1e-9))
        prior = max(0,after-1)
        def angle(i):
            q = np.asarray(trace[i]["quaternion_wxyz"])
            q0 = np.asarray(trace[0]["quaternion_wxyz"])
            dot = abs(np.dot(q, q0)/(np.linalg.norm(q)*np.linalg.norm(q0)))
            return math.degrees(2*math.acos(float(np.clip(dot,0.,1.))))
        row["rotation_guard"] = dict(native_stop_s=tm, commanded_phase=executed[prior][0],
                                     previous_saved_s=times[prior], previous_from_start_deg=angle(prior),
                                     next_saved_s=times[after], next_from_start_deg=angle(after),
                                     peak_from_start_deg=math.degrees(evidence["guard_facts"]["max_rotation_from_start_rad"]))
    events = raw.get("force_recovery",{}).get("events",[])
    samples = raw.get("force_recovery",{}).get("samples",np.empty((0,8)))
    for i, event in enumerate(events):
        next_trigger = events[i+1]["trigger_time_s"] if i+1 < len(events) else math.inf
        row["force_events"].append(describe_force(event, samples, receipt, trace, times,
                                                executed, source, evidence, next_trigger))
    row["search_after_force_count"] = sum(e["physical_chain_complete"] for e in row["force_events"])
    row["normal_recovery_requests"] = sum(e["reason"]=="B2_SEARCH_EXHAUSTED" for e in evidence["environment_events"])
    for label,key in (("decision","stop_time_s"),("task","task_end_time_s"),("audit","audit_end_time_s")):
        tm=receipt.get(key)
        row[key] = tm
        if tm is not None and times[0]-1e-9 <= tm <= times[-1]+1e-9:
            # Native stops can occur between recorded 2 ms poses. Keep their bracket explicit.
            lo=max(0,bisect_right(times,tm+1e-9)-1)
            frame=describe_pose(trace[lo],geom)
            frame["boundary_time_s"]=tm
            frame["following_saved_time_s"]=times[min(lo+1,len(times)-1)]
            row["frames"][label]=frame
    if not row["frames"].get("audit"):
        row["frames"]["last_saved"]=describe_pose(trace[-1],geom)
    decision = receipt.get("stop_time_s")
    relevant = bisect_right(times,decision+1e-9) if decision is not None else len(times)
    best=max(range(max(1,relevant)),key=lambda i: trace[i]["position_m"][2])
    row["frames"]["deepest_origin"]=describe_pose(trace[best],geom)
    for event in events:
        lo = max(0, bisect_right(times,event["trigger_time_s"]+1e-9)-1)
        key = f"pre_force_{event['id']}"
        row["frames"][key] = describe_pose(trace[lo],geom)
        row["frames"][key]["boundary_time_s"] = event["trigger_time_s"]
        row["frames"][key]["following_saved_time_s"] = times[min(lo+1,len(times)-1)]
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, default=DEFAULT)
    parser.add_argument("--episode", help="extract one completed archive to its own review JSON")
    parser.add_argument("--summary", action="store_true", help="combine previously extracted reviews")
    args = parser.parse_args()
    out=args.batch/"review"
    out.mkdir(exist_ok=True)
    if args.episode:
        from tools.validation.run_actor_lr_comparison import select_qualified_runtime
        select_qualified_runtime()
        from tools.model import layered_task
        row=review(args.batch/"run"/args.episode,layered_task)
        (out/(args.episode+".json")).write_text(json.dumps(row,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
        print(args.episode,row["receipt_status"],row["audit_verified"],row.get("search_after_force_count",0))
    elif args.summary:
        inputs=sorted(out.glob("*.json"))
        data=[json.loads(path.read_bytes()) for path in inputs]
        pins=[]
        for row in data:
            for name,frame in row.get("frames",{}).items():
                pins.extend(dict(episode_id=row["episode_id"], frame=name, time_s=frame["time_s"], **p) for p in frame["pins"])
        if pins:
            with (out/"per_pin.csv").open("w",encoding="utf-8-sig",newline="") as stream:
                writer=csv.DictWriter(stream,fieldnames=list(pins[0]))
                writer.writeheader()
                writer.writerows(pins)
        print("reviewed",len(data),"episodes,",len(pins),"pin-frame rows")
    else:
        parser.error("Choose an episode or --summary")


if __name__ == "__main__":
    main()
