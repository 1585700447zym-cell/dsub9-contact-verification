"""Read-only, bounded-memory comparisons of the fixed-weight load-warning retest."""
import argparse
from bisect import bisect_left, bisect_right
from collections import defaultdict
import csv
import gzip
import json
from pathlib import Path

from tools.validation.analyze_g1_recovery import JsonStream, describe_pose, sha

ROOT = Path(__file__).resolve().parents[2]
OLD = ROOT / "deliverables/learning_chain/g1_dynamic_900_20261105"
DT = .0002
PERIOD = .002


def discard_object(stream):
    for _ in stream.members(as_object=True):
        stream.discard()


def read_evidence(stream):
    result = {}
    keep = {"environment_events", "controller_events", "guard_facts", "interface_fault",
            "stop_time_s", "task_end_time_s", "audit_end_time_s"}
    for key in stream.members(as_object=True):
        if key in ("load_warnings", "force_recovery"):
            discard_object(stream)
        elif key in keep:
            result[key] = stream.value()
        else:
            stream.discard()
    return result


def read_compact(path, native_ticks=()):
    opener = gzip.open if path.suffix == ".gz" else open
    keep = {"case", "seed", "version", "episode_id", "policy_mode", "policy_source", "source_counts",
            "cumulative_peaks", "outcome", "cost", "error", "status", "stopped", "valid", "final_reason",
            "task_end_time_s", "stop_time_s", "audit_end_time_s", "archive_sha256", "finish_criteria",
            "dynamic_config", "model_xml_sha256", "reset_attempted", "reset_completed", "training_updates"}
    data = {}
    native_ticks = set(native_ticks)
    with opener(path, "rt", encoding="utf-8-sig") as handle:
        stream = JsonStream(handle)
        for key in stream.members(as_object=True):
            if key in keep:
                data[key] = stream.value()
            elif key == "load_warnings":
                summary = {}
                for field in stream.members(as_object=True):
                    if field == "samples":
                        selected = {}
                        for tick, _ in enumerate(stream.members(), 1):
                            row = stream.value()
                            if tick in native_ticks:
                                selected[tick] = row
                        data["selected_native"] = selected
                    else:
                        summary[field] = stream.value()
                data[key] = summary
            elif key in ("evidence", "evidence_before_abort"):
                data[key] = read_evidence(stream)
            elif key == "trace":
                fields = ("time_s", "position_m", "quaternion_wxyz", "phase", "policy_phase",
                          "velocity_world", "contact_wrench_M", "contact_wrench_G", "penetration_m")
                data[key] = [{name: row[name] for name in fields if name in row}
                             for _ in stream.members() for row in [stream.value()]]
            elif key == "transitions":
                data["executed"] = [(row["action_log"]["composition_inputs"]["phase"], row["action_active"], row["dt"])
                                    for _ in stream.members() for row in [stream.value()]]
            elif key == "source_cycles":
                data["source"] = [(row["phase"], row["enabled"])
                                  for _ in stream.members() for row in [stream.value()]]
            else:
                stream.discard()
        if stream.token():
            raise ValueError("Unexpected trailing JSON data")
    return data


def warning_summary(record, proof):
    """Use fully audited native exposure when available, retaining its exact source."""
    if proof:
        return proof
    # An incomplete audit cannot establish data eligibility. Only recorded totals
    # are shown here for diagnosis, with the failed-audit status on the episode.
    return dict(verified=False, peak_force_N=record.get("peak_force_N"),
                peak_rotation_rad=record.get("peak_rotation_rad"), events=record.get("events", []),
                metrics=record.get("metrics", {}), exposure=record.get("exposure", {}),
                recoveries=[], actual_search_resumptions=None)


def frame_at(trace, times, time, geometry):
    index = max(0, min(len(trace)-1, bisect_right(times, time+1e-9)-1))
    frame = trace[index]
    if geometry._pose(frame) is None:
        return dict(time_s=times[index], boundary_time_s=time, geometry_evaluable=False,
                    reason="Saved pose is outside the finite-cylinder referee's near-vertical domain", pins=[])
    result = describe_pose(frame, geometry)
    result.update(boundary_time_s=time, following_saved_time_s=times[min(index+1,len(times)-1)],
                  geometry_evaluable=True)
    return result


def describe_recoveries(audited, raw):
    trace = raw["trace"]
    times = [frame["time_s"] for frame in trace]
    events = raw["evidence"]["environment_events"]
    results = []
    for saved in audited:
        row = dict(saved)
        for name in ("start", "reached", "release"):
            value = saved.get(name+"_tick")
            row[name+"_s"] = None if value is None else value*DT
            row[name+"_native"] = raw.get("selected_native", {}).get(value)
        for name in ("reference_distance", "actual_at_reached", "actual_at_release"):
            value = saved.get(name+"_m")
            row[name+"_um"] = None if value is None else value*1e6
        row["executed_search_cycle"] = None
        release = row["release_s"]
        if release is not None:
            next_stop = min((e["time_s"] for e in events
                             if e["time_s"] > release+1e-9 and e.get("phase") in ("STOPPING","TERMINAL")),
                            default=times[-1])
            for i in range(bisect_left(times, release-1e-9), len(raw["executed"])):
                if times[i] >= next_stop-1e-9:
                    break
                if (raw["executed"][i][:2] == ("SEARCH", True) and raw["source"][i] == ("SEARCH", True)
                        and trace[i+1].get("policy_phase") == "SEARCH"):
                    row["executed_search_cycle"] = dict(cycle=i, start_s=times[i], end_s=times[i+1],
                                                       physical_phase_after=trace[i+1]["phase"])
                    break
        if bool(row["executed_search_cycle"]) != bool(saved["search_executed"]):
            raise ValueError("Read-back SEARCH execution disagrees with the native recovery proof")
        results.append(row)
    return results


def describe_warning_activity(native, raw, decision):
    """Separate threshold crossing from actual later control and final termination."""
    times = [frame["time_s"] for frame in raw["trace"]]
    first = {}
    for event in native["events"]:
        first.setdefault(event["reason"], event)
    result = {}
    for reason, event in first.items():
        start = event["start_time_s"]
        phases = defaultdict(float)
        first_active = None
        count = 0
        for i in range(bisect_left(times, start-1e-9), len(raw["executed"])):
            if decision is not None and times[i] >= decision-1e-9:
                break
            phase, enabled, dt = raw["executed"][i]
            if enabled and raw["source"][i] == (phase, True):
                if first_active is None:
                    first_active = dict(cycle=i, start_s=times[i], end_s=times[i+1],
                                        policy_phase=phase, physical_phase_after=raw["trace"][i+1]["phase"])
                count += 1
                phases[phase] += dt
        result[reason] = dict(first_native=raw.get("selected_native", {}).get(round(start/DT)),
                              first_event=event, first_later_enabled_cycle=first_active,
                              enabled_cycles_before_decision=count,
                              enabled_phase_durations_s=dict(phases),
                              time_to_decision_s=None if decision is None else decision-start)
    return result


def compare_before(old_id, raw, result):
    path = OLD/"review"/(old_id+".json")
    previous = json.loads(path.read_bytes())
    if previous["case"] != raw["case"]:
        raise ValueError("Old and new cases differ")
    for field in ("policy_mode", "actor_sha256", "exploration_seed", "deterministic", "hold_cycles", "period_s"):
        if previous["behavior"][field] != raw["policy_source"][field]:
            raise ValueError("Fixed-weight paired behavior differs: "+field)
    prior_receipt = json.loads((OLD/"run"/old_id/"receipt.json").read_bytes())
    if prior_receipt["seed"] != raw["seed"]:
        raise ValueError("Paired physical seed differs")
    previous_final = previous["frames"]["audit"]
    current_final = result["frames"].get("audit", result["frames"].get("last_saved", {}))
    gap = current_final.get("target_z_gap_mm")
    return dict(episode_id=old_id, immutable_previous_archive_sha256=previous["archive_sha256"],
                same_case=True, same_physical_seed=True, same_actor_parameters=True,
                same_exploration_seed=True, old_outcome=previous["outcome"],
                old_reason=previous["reason"], old_task_end_s=previous["task_end_time_s"],
                old_audit_end_s=previous["audit_end_time_s"], old_peak_force_N=previous["native_peaks"]["force_N"],
                task_end_delta_s=result["task_end_time_s"]-previous["task_end_time_s"],
                peak_force_delta_N=result["native_peaks"]["force_N"]-previous["native_peaks"]["force_N"],
                old_final=dict(time_s=previous_final["time_s"], position_mm=previous_final["position_mm"],
                               rpy_deg=previous_final["rpy_deg"], main_fit_count=previous_final["main_fit_count"],
                               present_worst_margin_um=previous_final["present_worst_margin_um"]),
                final_depth_gap_delta_mm=None if gap is None else gap-previous_final["target_z_gap_mm"],
                force_integral_comparison_available=False,
                force_integral_limitation="Old G1 archive lacks the same complete native force ledger; no exact integral comparison is claimed.",
                scope="Combined physical-rule change, no optimizer updates; success criteria and continuation rules differ.")


def review(folder, prior_id, geometry):
    receipt = read_compact(folder/"receipt.json")
    audit_path = folder/"audit.json"
    audit = json.loads(audit_path.read_bytes()) if audit_path.is_file() else {}
    result = dict(episode_id=folder.name, receipt_status=receipt["status"], outcome=receipt.get("outcome"),
                  reason=receipt.get("final_reason") or receipt.get("error"), audit_verified=audit.get("verified") is True,
                  task_end_time_s=receipt.get("task_end_time_s"), audit_end_time_s=receipt.get("audit_end_time_s"),
                  decision_time_s=receipt.get("stop_time_s"), case=receipt["case"],
                  physical_seed=receipt["seed"], audit_path=audit_path.relative_to(ROOT).as_posix() if audit else None)
    raw_path = folder/"episode.json.gz"
    if not raw_path.is_file():
        result["analysis_error"] = "No saved episode archive"
        return result
    result["archive_sha256"] = sha(raw_path)
    if result["archive_sha256"] != receipt["archive_sha256"]:
        raise ValueError("Receipt and archive SHA-256 differ")
    if audit and result["archive_sha256"] != audit["archive_sha256"]:
        raise ValueError("Audit and archive SHA-256 differ")
    if sha(folder/"model_used.xml") != receipt["model_xml_sha256"]:
        raise ValueError("Model bytes differ")
    proof = audit.get("load_warnings", {})
    native_ticks = {round(event["start_time_s"]/DT) for event in proof.get("events", [])}
    native_ticks.update(row[key] for row in proof.get("recoveries", [])
                        for key in ("start_tick", "reached_tick", "release_tick") if row.get(key) is not None)
    raw = read_compact(raw_path, native_ticks)
    result.update(source_mode=raw["policy_mode"], behavior=raw["policy_source"], cost=raw["cost"],
                  native_peaks=raw.get("cumulative_peaks"), outcome_evidence=raw["outcome"],
                  controller_events=raw["evidence"].get("controller_events"),
                  environment_events=raw["evidence"].get("environment_events"),
                  guard_facts=raw["evidence"].get("guard_facts"))
    native = warning_summary(raw["load_warnings"], audit.get("load_warnings", {}))
    result["native_load"] = native
    times = [frame["time_s"] for frame in raw["trace"]]
    if not times:
        result["analysis_error"] = "No completed trace"
        return result
    result["recoveries"] = describe_recoveries(native.get("recoveries", []), raw)
    result["warning_activity"] = describe_warning_activity(native, raw, receipt.get("stop_time_s"))
    frames = {}
    for label, key in (("decision","stop_time_s"),("task","task_end_time_s"),("audit","audit_end_time_s")):
        value = receipt.get(key)
        if value is not None:
            frames[label] = frame_at(raw["trace"], times, value, geometry)
    decision = receipt.get("stop_time_s")
    end = bisect_right(times,decision+1e-9) if decision is not None else len(times)
    best = max(range(max(1,end)),key=lambda i:raw["trace"][i]["position_m"][2])
    frames["deepest_origin"] = frame_at(raw["trace"], times, times[best], geometry)
    frames["deepest_origin"]["selection_scope"] = "Saved trace at or before decision stop; excludes later settling and audit tail"
    by_reason = {}
    for event in native["events"]:
        by_reason.setdefault(event["reason"], event)
    for reason, event in by_reason.items():
        frames["first_"+reason] = frame_at(raw["trace"], times, event["start_time_s"], geometry)
    result["frames"] = frames
    durations = defaultdict(float)
    for i,(phase,enabled,dt) in enumerate(raw["executed"]):
        if decision is not None and times[i] >= decision-1e-9:
            break
        durations[phase] += dt
    result["phase_times_before_decision_s"] = dict(durations)
    result["old_comparison"] = compare_before(prior_id,raw,result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch",type=Path,required=True)
    parser.add_argument("--episode")
    parser.add_argument("--prior-episode")
    parser.add_argument("--summary",action="store_true")
    args=parser.parse_args()
    args.batch=args.batch.resolve()
    out=args.batch/"review"
    out.mkdir(exist_ok=True)
    if args.episode:
        from tools.validation.run_actor_lr_comparison import select_qualified_runtime
        select_qualified_runtime()
        from tools.model import layered_task
        row=review(args.batch/"run"/args.episode,args.prior_episode or args.episode,layered_task)
        path=out/(args.episode+".json")
        path.write_text(json.dumps(row,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
        print(row["episode_id"],row["outcome"],row["audit_verified"],len(row.get("recoveries", [])))
    elif args.summary:
        rows=[json.loads(path.read_bytes()) for path in sorted(out.glob("*.json"))]
        pins=[]
        for row in rows:
            for label,frame in row.get("frames", {}).items():
                pins.extend(dict(episode_id=row["episode_id"],frame=label,time_s=frame["time_s"],**pin)
                            for pin in frame["pins"])
        if pins:
            with (out/"per_pin.csv").open("w",encoding="utf-8-sig",newline="") as stream:
                writer=csv.DictWriter(stream,fieldnames=list(pins[0]))
                writer.writeheader()
                writer.writerows(pins)
        print(len(rows),"episodes,",len(pins),"pin-frame rows")
    else:
        parser.error("An episode or --summary is required")


if __name__=="__main__":
    main()
