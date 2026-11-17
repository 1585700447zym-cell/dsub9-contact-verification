"""Independent native load/rotation warning audit. Reads records without running physics."""
import math
from tools.learning.five_axis_contract import WIDTH, field_slices
from tools.learning.observation import GUARDS


DT = .0002
PERIOD = .002
LIMITS = {
    "FORCE_GT5_N": ("force_N", 5.),
    "FORCE_GT6_N": ("force_N", 6.),
    "ROTATION_GT2P5_DEG": ("rotation_rad", math.radians(2.5)),
}
GUARD_SOURCE = "active_hard_guards_excluding_native_force_and_rotation_warnings"


def _number(value):
    if type(value) not in (float, int) or not math.isfinite(value):
        raise ValueError("Finite native scalar required")
    return value


def _same(actual, expected, *, counter=False, tol=1e-10):
    if counter:
        if type(actual) is not int or actual != expected:
            raise ValueError("Native counter differs")
    elif not math.isclose(_number(actual), expected, rel_tol=1e-11, abs_tol=tol):
        raise ValueError("Native measurement differs")


def _tick(time, size):
    tick = round(_number(time)/DT)
    if not 0 <= tick <= size or abs(time - tick*DT) > 1e-8:
        raise ValueError("Time outside registered native clock")
    return tick


def _bound(raw, receipt, key):
    value = raw["evidence"][key]
    if value != receipt.get(key) or value != raw.get(key):
        raise ValueError(f"Warning archive copies disagree for {key}")
    return value


def _angle(q, q0):
    # Shortest SO(3) angle from quaternion chord lengths, stable near zero and
    # invariant to quaternion sign. This is independent of the runtime guard.
    if len(q) != 4 or len(q0) != 4:
        raise ValueError("Quaternion required")
    norm = math.hypot(*map(_number, q))
    norm0 = math.hypot(*map(_number, q0))
    if not norm or not norm0:
        raise ValueError("Nonzero quaternion required")
    a = [v/norm for v in q]
    b = [v/norm0 for v in q0]
    minus, plus = math.dist(a,b), math.dist(a,[-v for v in b])
    return 4*math.atan2(min(minus, plus), max(minus, plus))


def _check_values(saved, expected):
    if not isinstance(saved, dict):
        raise ValueError("Missing native warning measurements")
    for key, value in expected.items():
        if key not in saved:
            raise ValueError(f"Missing native warning field {key}")
        _same(saved[key], value, counter=key in ("samples", "episodes"))


def _check_segments(record, samples):
    by_reason = {name: [] for name in LIMITS}
    for event in record["events"]:
        if event.get("reason") not in LIMITS:
            raise ValueError("Unexpected warning event")
        by_reason[event["reason"]].append(event)
    if record["metrics"].keys() != LIMITS.keys():
        raise ValueError("Incomplete warning metrics")
    for reason, (field, limit) in LIMITS.items():
        spans = []
        event = None
        for sample in samples:
            value = sample[field]
            if value <= limit:
                event = None
                continue
            if event is None:
                event = dict(start_time_s=sample["time_s"], samples=0, peak=0., excess_integral=0.)
                spans.append(event)
            event["last_time_s"] = sample["time_s"]
            event["samples"] += 1
            event["peak"] = max(event["peak"], value)
            event["duration_s"] = event["samples"]*DT
            event["excess_integral"] += (value-limit)*DT
        if len(spans) != len(by_reason[reason]):
            raise ValueError("Warning intervals differ")
        for expected, saved in zip(spans, by_reason[reason]):
            _check_values(saved, expected)
        count = sum(e["samples"] for e in spans)
        _check_values(record["metrics"][reason], dict(samples=count, episodes=len(spans),
            duration_s=count*DT, peak=max((e["peak"] for e in spans), default=0.),
            excess_integral=sum((e["excess_integral"] for e in spans), 0.)))


def _exposure(samples, saved):
    count = len(samples)
    duration = count*DT
    integral = math.fsum(s["force_N"] for s in samples)*DT
    square = math.fsum(s["force_N"]**2 for s in samples)*DT
    result = dict(samples=count, duration_s=duration, integral_force_Ns=integral, square_integral_force_N2s=square)
    _check_values(saved, result)
    result.update(mean_force_N=integral/duration if count else None,
                  rms_force_N=math.sqrt(square/duration) if count else None)
    # Split crossing durations at the task/audit boundary, even for one
    # continuous event spanning that boundary.
    result["warnings"] = {}
    for reason, (field, limit) in LIMITS.items():
        length = longest = total = 0
        peak = max(samples,key=lambda s:s[field],default=None)
        for sample in samples:
            length = length+1 if sample[field] > limit else 0
            total += int(length > 0)
            longest = max(longest,length)
        result["warnings"][reason] = dict(over_duration_s=total*DT, longest_continuous_s=longest*DT,
            peak=peak[field] if peak else None, peak_time_s=peak["time_s"] if peak else None)
    return result


def _check_native(samples, peaks, trace):
    for tick, sample in enumerate(samples, 1):
        if _tick(sample["time_s"],len(samples)) != tick or sample["phase"] not in ("RUNNING","RETRACT","STOPPING"):
            raise ValueError("Missing or out-of-order native sample")
        if any(_number(sample[k]) < 0 for k in
               ("force_N","rotation_rad","linear_m_s","angular_rad_s","torque_G_Nm","penetration_m")):
            raise ValueError("Negative native magnitude")
        if sample["rotation_rad"] > math.pi+1e-12:
            raise ValueError("Not a shortest SO(3) angle")
        _number(sample["position_z_m"])
        _number(sample["reference_z_m"])
    for i, peak in enumerate(peaks):
        native = samples[i*10:i*10+10]
        _check_values(peak, dict(samples=10,
            **{key:max(s[key] for s in native) for key in ("force_N","torque_G_Nm","penetration_m")}))
        frame = trace[i+1]
        if _tick(frame["time_s"],len(samples)) != (i+1)*10:
            raise ValueError("Native/control endpoint clock differs")
        _check_values(native[-1], dict(
            force_N=math.hypot(*frame["contact_wrench_M"][:3]),
            torque_G_Nm=math.hypot(*frame["contact_wrench_G"][3:]), penetration_m=frame["penetration_m"],
            rotation_rad=_angle(frame["quaternion_wxyz"],trace[0]["quaternion_wxyz"]),
            linear_m_s=math.hypot(*frame["velocity_world"][:3]), angular_rad_s=math.hypot(*frame["velocity_world"][3:]),
            position_z_m=frame["position_m"][2]))


def _recovery_rows(raw, samples, dynamic, min_actual):
    """Separate a requested reference target from the physical pose at release."""
    results = []
    active = None
    trace = raw["trace"]
    source = raw["source_cycles"]
    # Reconstruct RETRACT intervals from the independently logged physical
    # transitions; a removed recovery event must not hide physical retraction.
    phase = "RUNNING"
    changes = {}
    for event in raw["evidence"]["environment_events"]:
        if event.get("phase") is not None:
            tick = _tick(event["time_s"],len(samples))
            changes.setdefault(tick,[]).append(event["phase"])
    for tick, sample in enumerate(samples, 1):
        for following in changes.get(tick-1,()):
            phase = following
        if (phase=="RETRACT") != (sample["phase"]=="RETRACT") and sample["phase"] not in changes.get(tick,()):
            raise ValueError("Native retraction phases disagree with physical events")
    for event in raw["evidence"]["environment_events"]:
        why = event.get("reason", "")
        reasons = {part.strip() for part in why.split("+") if part.strip()}
        warning_reasons = set(LIMITS) | {"FORCE_LIMIT","ROTATION_LIMIT","FORCE_FATAL_CEILING",
                                        "FORCE_PERSISTENT","FORCE_RECURRENCE","FORCE_RECOVERY_NOT_ELIGIBLE"}
        if reasons and reasons <= warning_reasons and event.get("phase") == "STOPPING":
            raise ValueError("A warning alone stopped physics")
        if why not in ("RECOVERY_ACCEPTED","RECOVERY_DISTANCE_REACHED","B2_RECOVERY_RESUMED"):
            continue
        tick = _tick(event["time_s"],len(samples))
        if not tick:
            raise ValueError("Missing native recovery pose")
        sample = samples[tick-1]
        if why == "RECOVERY_ACCEPTED":
            if (active is not None or event.get("phase") != "RETRACT" or tick % 10
                    or sample["force_N"] > dynamic["recovery_force_N"]
                    or sample["torque_G_Nm"] > dynamic["stop_torque_Nm"]
                    or sample["penetration_m"] >= dynamic["stop_penetration_m"]
                    or sample["linear_m_s"] > dynamic["stopped_speed"]
                    or sample["angular_rad_s"] > dynamic["stopped_angular_speed"]):
                raise ValueError("Invalid recovery start")
            active = dict(start_tick=tick, start_z_m=sample["position_z_m"], reached_tick=None, release_tick=None,
                          search_executed=False)
            results.append(active)
        elif why == "RECOVERY_DISTANCE_REACHED":
            if (active is None or active["reached_tick"] is not None or tick <= active["start_tick"]
                    or event.get("phase") != "STOPPING"):
                raise ValueError("Invalid recovery target event")
            ref = active["start_z_m"]-sample["reference_z_m"]
            if ref < dynamic["recovery_distance_m"]-1e-12:
                raise ValueError("Reference retraction target was not reached")
            active.update(reached_tick=tick, reference_distance_m=ref,
                          actual_at_reached_m=active["start_z_m"]-sample["position_z_m"])
        else:
            if (active is None or active["reached_tick"] is None or tick < active["reached_tick"]
                    or event.get("phase") != "RUNNING" or tick % 10):
                raise ValueError("Invalid recovery release")
            distance = active["start_z_m"]-sample["position_z_m"]
            if distance < min_actual-1e-15:
                raise ValueError("Actual release retraction below relaxed minimum")
            if (sample["force_N"] > dynamic["recovery_force_N"] or sample["torque_G_Nm"] > dynamic["stop_torque_Nm"]
                    or sample["penetration_m"] >= dynamic["stop_penetration_m"]
                    or sample["linear_m_s"] > dynamic["stopped_speed"]
                    or sample["angular_rad_s"] > dynamic["stopped_angular_speed"]):
                raise ValueError("Recovery released under load or before stable")
            cycle = tick//10
            # At the resume boundary, the already-frozen previous trace can
            # still say STOPPING; the first applied control row is decisive.
            active.update(release_tick=tick, actual_at_release_m=distance,
                          search_executed=(cycle < len(source) and source[cycle].get("phase") == "SEARCH"
                              and source[cycle].get("enabled") is True and trace[cycle+1].get("policy_phase") == "SEARCH"))
            active = None
    return results


def verify_load_warnings(raw, receipt, contract):
    """Verify the three stored copies against all native cycles and saved endpoints."""
    record = _bound(raw, receipt, "load_warnings")
    cumulative = _bound(raw, receipt, "cumulative_peaks")
    peaks, trace = raw["cycle_peaks"], raw["trace"]
    facts = raw["evidence"]["guard_facts"]
    dynamic = receipt["dynamic_config"]
    settings = contract["load_warning"]
    if (settings["version"] != "native_load_warnings_v1" or settings["force_warning_N"] != [5.,6.]
            or settings["rotation_warning_rad"] != LIMITS["ROTATION_GT2P5_DEG"][1]
            or settings["force_success_gate"] is not False
            or settings["recovery_reference_target_m"] != .0003 or dynamic["recovery_distance_m"] != .0003
            or settings["recovery_effective_min_actual_m"] != .000249):
        raise ValueError("Frozen warning and retraction criteria differ")
    if facts != receipt["guard_facts"] or record.get("version") != "native_load_warnings_v1":
        raise ValueError("Warning version or historical facts differ")
    schema = [f for f in raw["observation_schema"] if f.get("name")=="latched_guards"]
    if len(schema)!=1 or schema[0].get("source") != GUARD_SOURCE:
        raise ValueError("Warning facts cannot block the policy observation")
    start = field_slices()["latched_guards"].start
    warning_slots = [start + GUARDS.index(name) for name in ("FORCE_LIMIT", "ROTATION_LIMIT")]
    rows = raw["transitions"]
    if len(rows) != len(peaks):
        raise ValueError("A policy transition is required for each warning control cycle")
    for row in rows:
        for key in ("observation", "next_observation"):
            frame = row[key]
            if len(frame) != WIDTH or any(frame[slot] != 0 for slot in warning_slots):
                raise ValueError("Historical warning cannot block a policy observation")
    if (dynamic["timestep"] != DT or dynamic["control_period"] != PERIOD or
            contract["control_period_s"] != PERIOD or record["timestep_s"] != DT):
        raise ValueError("Registered warning clock required")
    samples = record["samples"]
    if not isinstance(samples,list) or not peaks or len(samples) != len(peaks)*10 or len(trace) != len(peaks)+1:
        raise ValueError("Incomplete native load warning record")
    _same(record["checked_substeps"],len(samples),counter=True)
    _same(facts["checked_substeps"],len(samples),counter=True)
    _check_native(samples,peaks,trace)
    max_force = max(p["force_N"] for p in peaks)
    max_angle = max(s["rotation_rad"] for s in samples)
    _check_values(record,dict(peak_force_N=max_force,peak_rotation_rad=max_angle))
    _same(facts["max_rotation_from_start_rad"],max_angle)
    for key, reason, limit in (("force_N","FORCE_LIMIT",5.),("torque_G_Nm","TORQUE_LIMIT",.1),
                               ("penetration_m","PENETRATION_LIMIT",.00003)):
        value = max(p[key] for p in peaks)
        _same(cumulative[key],value)
        if (value > limit) != (reason in facts["contact_reasons"]):
            raise ValueError("Historical contact facts differ from native measurements")
    if (max_angle > LIMITS["ROTATION_GT2P5_DEG"][1]) != ("ROTATION_LIMIT" in facts["motion_reasons"]):
        raise ValueError("Historical rotation warning does not match native angles")
    for field,reason,limit_key in (("linear_m_s","SPEED_LIMIT","actual_speed_limit"),
                                  ("angular_rad_s","ANGULAR_SPEED_LIMIT","actual_angular_speed_limit")):
        maximum = max(s[field] for s in samples)
        if (maximum > _number(dynamic[limit_key])) != (reason in facts["motion_reasons"]):
            raise ValueError("Historical speed protection differs from native measurements")
        if field == "linear_m_s" and "speed_m_s" in cumulative:
            _same(cumulative["speed_m_s"],maximum)
    task_end = raw["evidence"]["task_end_time_s"]
    _same(record["task_end_time_s"],_number(task_end))
    _same(receipt["task_end_time_s"],task_end)
    task_tick = _tick(task_end,len(samples))
    if (_tick(raw["evidence"]["audit_end_time_s"],len(samples)) != len(samples)
            or _tick(receipt["audit_end_time_s"],len(samples)) != len(samples)):
        raise ValueError("Native warning ledger misses the recorded audit end")
    _check_segments(record,samples)
    exposure = {name:_exposure(data,record["exposure"][name]) for name,data in
                (("all",samples),("task",samples[:task_tick]),("audit_tail",samples[task_tick:]))}
    recoveries = _recovery_rows(raw,samples,dynamic,settings["recovery_effective_min_actual_m"])
    return dict(verified=True, native_samples=len(samples), peak_force_N=max_force, peak_rotation_rad=max_angle,
                events=record["events"], metrics=record["metrics"], exposure=exposure, recoveries=recoveries,
                actual_search_resumptions=sum(r["search_executed"] for r in recoveries))
