"""Independent synthetic native ledger and archive tampering checks; no simulator."""
from copy import deepcopy
from importlib.util import find_spec
import math

import pytest
from tools.learning.five_axis_contract import WIDTH, field_slices
from tools.learning.observation import GUARDS


DT = .0002
LIMIT = math.radians(2.5)
THRESHOLDS = dict(FORCE_GT5_N=5., FORCE_GT6_N=6., ROTATION_GT2P5_DEG=LIMIT)


def verify(raw, receipt, contract):
    assert find_spec("tools.validation.load_warning_audit"), "Native warning auditor required"
    from tools.validation.load_warning_audit import verify_load_warnings
    return verify_load_warnings(raw, receipt, contract)


def policy_row():
    return dict(observation=[0.]*WIDTH, next_observation=[0.]*WIDTH)


def native_fixture():
    forces = [0.] * 30
    forces[8:12] = [5., 5.5, 6.5, 6.25]   # Cross-cycle event; 5.0 itself is not above.
    forces[21] = 5.2
    angles = [0.] * 30
    angles[3:5] = [LIMIT, LIMIT + .001]
    samples = []
    for i, (force, angle) in enumerate(zip(forces, angles), start=1):
        samples.append(dict(time_s=i*DT, phase="RUNNING", force_N=force, rotation_rad=angle,
            position_z_m=0., reference_z_m=0., linear_m_s=0., angular_rad_s=0., torque_G_Nm=0., penetration_m=0.))
    spans = dict(FORCE_GT5_N=[(10, 12), (22, 22)], FORCE_GT6_N=[(11, 12)], ROTATION_GT2P5_DEG=[(5, 5)])
    events, metrics = [], {}
    for reason, ranges in spans.items():
        values = angles if reason.startswith("ROTATION") else forces
        limit = THRESHOLDS[reason]
        local = []
        for first, last in ranges:
            sl = values[first-1:last]
            local.append(dict(reason=reason,start_time_s=first*DT,last_time_s=last*DT,samples=len(sl),
                peak=max(sl),duration_s=len(sl)*DT,excess_integral=sum(x-limit for x in sl)*DT))
        events.extend(local)
        metrics[reason] = dict(samples=sum(e["samples"] for e in local), episodes=len(local),
            duration_s=sum(e["duration_s"] for e in local),peak=max(e["peak"] for e in local),
            excess_integral=sum(e["excess_integral"] for e in local))

    def exposure(values):
        return dict(samples=len(values),duration_s=len(values)*DT,integral_force_Ns=sum(values)*DT,
                    square_integral_force_N2s=sum(v*v for v in values)*DT)

    record = dict(version="native_load_warnings_v1", checked_substeps=30, timestep_s=DT,
        peak_force_N=max(forces), peak_rotation_rad=max(angles), task_end_time_s=.004,
        samples=samples, events=events, metrics=metrics,
        exposure=dict(all=exposure(forces),task=exposure(forces[:20]),audit_tail=exposure(forces[20:])))
    facts = dict(simulation_valid=True, invalid_reasons=[], contact_reasons=["FORCE_LIMIT"],
                 motion_reasons=["ROTATION_LIMIT"], checked_substeps=30, max_rotation_from_start_rad=max(angles))
    frames = []
    for i in range(0, 31, 10):
        f = forces[i-1] if i else 0.
        angle = angles[i-1] if i else 0.
        frames.append(dict(time_s=i*DT, position_m=[0.,0.,0.], quaternion_wxyz=[math.cos(angle/2),0.,0.,math.sin(angle/2)],
            velocity_world=[0.]*6,contact_wrench_M=[f,0.,0.,0.,0.,0.],contact_wrench_G=[f,0.,0.,0.,0.,0.],
            penetration_m=0.,phase="RUNNING"))
    peaks = [dict(force_N=max(forces[k:k+10]), torque_G_Nm=0., penetration_m=0., samples=10) for k in (0,10,20)]
    common = dict(stopped_speed=1e-5,stopped_angular_speed=.001,recovery_force_N=.5,stop_torque_Nm=.1,
                  actual_speed_limit=.02, actual_angular_speed_limit=.5,
                  stop_penetration_m=.00003,recovery_distance_m=.0003, control_period=.002,timestep=DT)
    from tools.learning.load_warning_trial import protocol_config
    physical = protocol_config(900)
    cumulative=dict(force_N=max(forces),torque_G_Nm=0.,penetration_m=0.)
    raw=dict(trace=frames,cycle_peaks=peaks,source_cycles=[],cumulative_peaks=cumulative,
        transitions=[policy_row() for _ in peaks],
        observation_schema=[dict(name="latched_guards",source="active_hard_guards_excluding_native_force_and_rotation_warnings")],
        evidence=dict(environment_events=[],guard_facts=facts,task_end_time_s=.004,audit_end_time_s=.006))
    receipt=dict(guard_facts=deepcopy(facts), task_end_time_s=.004, audit_end_time_s=.006, dynamic_config=common,
        cumulative_peaks=deepcopy(cumulative))
    raw["evidence"]["cumulative_peaks"]=deepcopy(cumulative)
    for obj in (raw,raw["evidence"],receipt):
        obj["load_warnings"]=deepcopy(record)
    return raw,receipt,physical


def test_native_exposure_thresholds_and_cross_cycle_intervals():
    raw,receipt,contract=native_fixture()
    p=verify(raw,receipt,contract)
    assert p["verified"] and p["native_samples"]==30
    assert p["metrics"]["FORCE_GT5_N"]["duration_s"]==pytest.approx(4*DT)
    assert p["exposure"]["audit_tail"]["mean_force_N"]==pytest.approx(.52)
    assert p["exposure"]["all"]["rms_force_N"]==pytest.approx(math.sqrt(sum(x["force_N"]**2 for x in raw["load_warnings"]["samples"])/30))
    assert p["recoveries"]==[]


def test_actual_telemetry_producer_and_independent_rows_agree():
    from tools.learning.load_warning_trial import summarize_warnings
    raw,receipt,contract=native_fixture()
    native=summarize_warnings(raw["load_warnings"]["samples"],task_end_time_s=.004)
    for obj in (raw,raw["evidence"],receipt):
        obj["load_warnings"]=deepcopy(native)
    assert verify(raw,receipt,contract)["metrics"]["FORCE_GT5_N"]["episodes"]==2


def test_native_zero_warning_metrics_accept_real_float_zeros():
    from tools.learning.load_warning_trial import summarize_warnings
    raw,receipt,contract=native_fixture()
    quiet=[dict(s,force_N=0.,rotation_rad=0.) for s in raw["load_warnings"]["samples"]]
    record=summarize_warnings(quiet,task_end_time_s=.004)
    for frame in raw["trace"]:
        frame["contact_wrench_M"]=[0.]*6
        frame["contact_wrench_G"]=[0.]*6
    for peak in raw["cycle_peaks"]:
        peak["force_N"]=0.
    raw["evidence"]["guard_facts"].update(contact_reasons=[],motion_reasons=[],max_rotation_from_start_rad=0.)
    receipt["guard_facts"]=deepcopy(raw["evidence"]["guard_facts"])
    for obj in (raw,raw["evidence"],receipt):
        obj["load_warnings"]=deepcopy(record)
        obj["cumulative_peaks"]["force_N"]=0.
    assert verify(raw,receipt,contract)["events"]==[]


@pytest.mark.parametrize("field,reason,value", [("linear_m_s","SPEED_LIMIT",.021),
                                                ("angular_rad_s","ANGULAR_SPEED_LIMIT",.51)])
@pytest.mark.parametrize("forged_fact", [False,True])
def test_inside_cycle_speed_and_facts_must_agree(field, reason, value, forged_fact):
    raw,receipt,contract=native_fixture()
    for obj in (raw,raw["evidence"],receipt):
        if not forged_fact:
            obj["load_warnings"]["samples"][2][field]=value
    if forged_fact:
        raw["evidence"]["guard_facts"]["motion_reasons"].append(reason)
        receipt["guard_facts"]=deepcopy(raw["evidence"]["guard_facts"])
    with pytest.raises(ValueError,match="speed"):
        verify(raw,receipt,contract)


def test_cumulative_speed_when_recorded_matches_native_peak():
    raw,receipt,contract=native_fixture()
    for obj in (raw,raw["evidence"],receipt):
        obj["cumulative_peaks"]["speed_m_s"]=.001
    with pytest.raises(ValueError):
        verify(raw,receipt,contract)


def test_combined_warning_only_cannot_issue_stop_but_concurrent_hard_guards_can():
    raw,receipt,contract=native_fixture()
    event=dict(reason="FORCE_LIMIT+ROTATION_LIMIT",phase="STOPPING",time_s=.006)
    raw["evidence"]["environment_events"].append(event)
    with pytest.raises(ValueError,match="warning"):
        verify(raw,receipt,contract)
    # Keep real evidence for the concurrent hard guard.
    event["reason"] += "+TORQUE_LIMIT"
    for obj in (raw,raw["evidence"],receipt):
        obj["load_warnings"]["samples"][29]["torque_G_Nm"]=.11
        obj["cumulative_peaks"]["torque_G_Nm"]=.11
    raw["cycle_peaks"][2]["torque_G_Nm"]=.11
    raw["trace"][3]["contact_wrench_G"][3]=.11
    raw["evidence"]["guard_facts"]["contact_reasons"].append("TORQUE_LIMIT")
    receipt["guard_facts"]=deepcopy(raw["evidence"]["guard_facts"])
    assert verify(raw,receipt,contract)["verified"]


@pytest.mark.parametrize("reason", ["FORCE_LIMIT", "ROTATION_LIMIT"])
@pytest.mark.parametrize("frame", ["observation", "next_observation"])
def test_history_warnings_cannot_block_policy_inputs(reason, frame):
    raw, receipt, contract = native_fixture()
    # Leave the historical facts and warning schema untouched. A source using
    # this wrong bit could consistently disable actions and replay them as zero.
    slot = field_slices()["latched_guards"].start + GUARDS.index(reason)
    raw["transitions"][1][frame][slot] = 1.
    with pytest.raises(ValueError, match="warning.*policy"):
        verify(raw, receipt, contract)


@pytest.mark.parametrize("kind", ["copies","clock","facts","rotation_fact","running_peak","loss_of_episode",
                                   "duration","exposure","trace","rotation","cycle","task_boundary","endpoint_facts"])
def test_tampering_is_rejected(kind):
    raw,receipt,contract=native_fixture()
    record=raw["load_warnings"]
    if kind=="copies": receipt["load_warnings"]["peak_force_N"]=0.
    elif kind=="clock": record["samples"][15]["time_s"]+=DT
    elif kind=="facts": raw["evidence"]["guard_facts"]["contact_reasons"]=[]
    elif kind=="rotation_fact": raw["evidence"]["guard_facts"]["motion_reasons"]=[]
    elif kind=="running_peak": record["peak_force_N"]=42.
    elif kind=="loss_of_episode": record["events"].pop()
    elif kind=="duration": record["metrics"]["FORCE_GT5_N"]["duration_s"]=0.
    elif kind=="exposure": record["exposure"]["task"]["integral_force_Ns"]=0.
    elif kind=="trace": raw["trace"][1]["contact_wrench_M"][0]+=1.
    elif kind=="rotation": raw["trace"][1]["quaternion_wxyz"]=[0.,0.,0.,1.]
    elif kind=="cycle": raw["cycle_peaks"][0]["force_N"]=6.75
    elif kind=="task_boundary": record["task_end_time_s"]+=DT
    elif kind=="endpoint_facts": raw["evidence"]["guard_facts"]["max_rotation_from_start_rad"]=0.
    if kind!="copies":
        for obj in (raw["evidence"],receipt): obj["load_warnings"]=deepcopy(record)
        receipt["guard_facts"]=deepcopy(raw["evidence"]["guard_facts"])
    with pytest.raises(ValueError):
        verify(raw,receipt,contract)

def recovery_fixture():
    raw, receipt, contract = native_fixture()
    record = raw["load_warnings"]
    samples = record["samples"]
    # Zero dwell is not assumed. Hold two control cycles at the target, with
    # 249.5 um physical clearance after rebound, then execute a SEARCH row.
    start, reached, release = 30, 3230, 3250
    for k in range(start+1, release+11):
        fraction = min(1., (k-start)/(reached-start))
        moving = k <= reached
        z = -.00025*fraction if moving else -.0002495
        samples.append(dict(samples[-1], time_s=k*DT, phase="RETRACT" if moving else
                            "STOPPING" if k<=release else "RUNNING", force_N=0.,rotation_rad=0.,
                            position_z_m=z, reference_z_m=-.0003*fraction, linear_m_s=0.))
    for tick in range(start+10,len(samples)+1,10):
        s=samples[tick-1]
        raw["trace"].append(dict(raw["trace"][0],time_s=tick*DT, position_m=[0.,0.,s["position_z_m"]],
            phase=s["phase"], policy_phase="SEARCH" if tick>release else "WAIT_RECOVERY"))
        raw["cycle_peaks"].append(dict(force_N=0.,torque_G_Nm=0.,penetration_m=0.,samples=10))
        raw["transitions"].append(policy_row())
    ev=[("B2_SEARCH_EXHAUSTED","STOPPING",20), ("RECOVERY_ACCEPTED","RETRACT",start),
        ("RECOVERY_DISTANCE_REACHED","STOPPING",reached), ("B2_RECOVERY_RESUMED","RUNNING",release)]
    raw["evidence"]["environment_events"]=[dict(reason=why,phase=phase,time_s=tick*DT) for why,phase,tick in ev]
    raw["source_cycles"]=[dict(phase="SEARCH" if k==release//10 else "WAIT_RECOVERY",enabled=k==release//10)
                          for k in range(len(raw["cycle_peaks"]))]
    count=len(samples)
    raw["evidence"]["guard_facts"]["checked_substeps"]=count
    receipt["guard_facts"]=deepcopy(raw["evidence"]["guard_facts"])
    record.update(checked_substeps=count,task_end_time_s=release*DT)
    raw["evidence"].update(task_end_time_s=release*DT,audit_end_time_s=count*DT)
    receipt.update(task_end_time_s=release*DT,audit_end_time_s=count*DT)
    for name, segment in (("all",samples),("task",samples[:release]),("audit_tail",samples[release:])):
        record["exposure"][name]=dict(samples=len(segment),duration_s=len(segment)*DT,
            integral_force_Ns=sum(s["force_N"] for s in segment)*DT,
            square_integral_force_N2s=sum(s["force_N"]**2 for s in segment)*DT)
    raw["evidence"]["load_warnings"]=deepcopy(record)
    receipt["load_warnings"]=deepcopy(record)
    return raw,receipt,contract


def test_reference_target_and_actual_release_are_separate_and_search_is_observed():
    raw,receipt,contract=recovery_fixture()
    result=verify(raw,receipt,contract)
    recovered=result["recoveries"][0]
    assert recovered["reference_distance_m"]==pytest.approx(.0003)
    assert recovered["actual_at_reached_m"]==pytest.approx(.00025)
    assert recovered["actual_at_release_m"]==pytest.approx(.0002495)
    assert result["actual_search_resumptions"]==1
    raw["source_cycles"][-1]["enabled"]=False
    assert verify(raw,receipt,contract)["actual_search_resumptions"]==0


@pytest.mark.parametrize("kind",["actual","reference","hard_contact","guard_source","late_motion"])
def test_forged_recovery_hard_protection_or_schema_is_rejected(kind):
    raw,receipt,contract=recovery_fixture()
    if kind in ("actual","reference"):
        tick=3250 if kind=="actual" else 3230
        if kind=="actual":
            raw["load_warnings"]["samples"][tick-1]["position_z_m"]=-.0002489
            raw["trace"][tick//10]["position_m"][2]=-.0002489
        else:
            raw["load_warnings"]["samples"][tick-1]["reference_z_m"]=-.00025
        for obj in (raw["evidence"],receipt): obj["load_warnings"]=deepcopy(raw["load_warnings"])
    elif kind=="hard_contact":
        raw["evidence"]["guard_facts"]["contact_reasons"].append("TORQUE_LIMIT")
        receipt["guard_facts"]=deepcopy(raw["evidence"]["guard_facts"])
    elif kind=="guard_source":
        raw["observation_schema"][0]["source"]="old_fatal_force"
    else:
        raw["evidence"]["environment_events"][-1]["phase"]="STOPPING"
    with pytest.raises(ValueError): verify(raw,receipt,contract)
