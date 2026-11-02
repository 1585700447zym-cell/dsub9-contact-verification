"""Saved evidence analysis only; fixtures never initialize a physics engine."""
import gzip
import hashlib
import importlib
import json
from pathlib import Path

import numpy as np
import pytest


def api():
    return importlib.import_module('tools.validation.analyze_global_residual_authority')


def episode(end=1.8):
    # +yaw completes at 1.2; -yaw is interrupted at 1.8, before its 2.4 end.
    times = np.round(np.arange(0, end + .05, .1), 10)
    trace = [dict(time_s=float(t), position_m=[t * 1e-6, 0., -.004],
                  quaternion_wxyz=[1., 0., 0., 0.], velocity_world=[1e-6, 0., 0., 0., 0., 0.],
                  limited_command_world=[0.] * 6, reference_qpos=[0., 0., -.004, 1., 0., 0., 0.],
                  contact_wrench_M=[0., 0., 2., 0., 0., .01],
                  phase='RUNNING' if t < end else 'STOPPING', contact_count=1) for t in times]
    transitions = []
    for t in times[:-1]:
        action = [0.] * 5
        for start, sign in ((.2, 1), (1.4, -1)):
            if start < t < start + 1:
                action[4] = sign * min((t-start)/.2, 1., (start+1-t)/.2)
        request = [0., 0., 0., 0., 0., action[4] * .005]
        transitions.append(dict(dt=.1, action=action, action_active=True,
            action_log=dict(raw_action=action, requested_residual=request,
                applied_residual=request, profile='G1',
                composition_inputs=dict(base_command=[0.]*6, phase='SEARCH', dt=.1),
                pre_stage_total=request, stage_clip_delta=[0.]*6, drive_clip_delta=[0.]*6,
                unfiltered_stage_limited_total=request, stage_limited_total=request,
                predicted_limited_command=request, effective_command_delta=request,
                reference_filter_fraction=1.)))
    return dict(trace=trace, transitions=transitions, cycle_peaks=[],
        outcome=dict(simulation_valid=True, task_outcome='TIME_LIMIT'),
        evidence=dict(stop_time_s=end, environment_events=[],
            controller_events=[dict(time_s=0., reason='LOW_LOAD_SEARCH', phase='SEARCH'),
                               dict(time_s=end, reason='SEARCH_INTERRUPTED', phase='UNLOAD')],
            guard_facts=dict(contact_reasons=[], motion_reasons=[], invalid_reasons=[])))


def test_completed_and_interrupted_pulses_do_not_invent_remaining_coverage():
    m = api()
    result = m.analyze_episode(episode(), geometry=m.read_pin_geometry())
    pulses = result['pulses']
    assert [p['status'] for p in pulses] == [
        'completed', 'interrupted', 'not_covered', 'not_covered', 'not_covered', 'not_covered']
    assert pulses[0]['normalized_request_integral_s'] == pytest.approx(.8)
    assert pulses[0]['command']['physical_request_integral'][5] == pytest.approx(.004)
    assert pulses[0]['motion']['displacement_xy_um'][0] == pytest.approx(.9)
    assert result['snapshots']['at_25s'] is None
    assert result['snapshots']['task_stop']['time_s'] == 1.8
    assert result['new_physical_substeps'] == 0


def test_geometry_distinguishes_entry_necessary_condition_from_main_occupancy():
    m = api()
    geometry = m.read_pin_geometry()
    row = dict(position_m=[0., 0., -.0039], quaternion_wxyz=[1., 0., 0., 0.], time_s=0.)
    before = m.geometry_snapshot(row, geometry)
    assert len(before['pins']) == 9
    assert before['all_nine_entry_centerline_necessary_condition'] is True
    assert before['main_plane_overlap_pin_count'] == 0
    assert before['pins'][0]['entry_centerline_clearance_um'] == pytest.approx(175.)
    row['position_m'][2] = -.0037
    after = m.geometry_snapshot(row, geometry)
    assert after['main_plane_overlap_pin_count'] == 9
    assert 'full_success' not in after


def test_invalid_or_missing_trace_remains_reportable_without_geometry_claim():
    m = api()
    result = m.analyze_episode(dict(trace=[], transitions=[], outcome={
        'simulation_valid': False, 'task_outcome': 'INVALID_SIMULATION'}), geometry=m.read_pin_geometry())
    assert result['diagnostic_status'] == 'no_trace'
    assert result['snapshots'] == {'at_25s': None, 'task_stop': None}
    assert all(p['status'] == 'not_covered' for p in result['pulses'])
    raw = episode()
    raw['outcome']['simulation_valid'] = False
    raw['trace'][2]['position_m'][0] = float('nan')
    result = m.analyze_episode(raw, geometry=m.read_pin_geometry())
    assert result['diagnostic_status'] == 'partial_trace'
    assert result['trace_rows_rejected'] == 1
    assert result['outcome']['simulation_valid'] is False


def test_clipping_duration_is_axis_specific_and_physical_motion_is_separate():
    m = api()
    raw = episode()
    log = raw['transitions'][3]['action_log']
    log['stage_clip_delta'] = [-.00005, 0., 0., 0., 0., -.001]
    log['drive_clip_delta'] = [0., 0., 0., 0., 0., -.0001]
    log['reference_filter_fraction'] = .5
    result = m.analyze_episode(raw, geometry=m.read_pin_geometry())
    command = result['pulses'][0]['command']
    assert command['stage_clip_duration_s'] == pytest.approx([.1, 0., 0., 0., 0., .1])
    assert command['drive_clip_duration_s'] == pytest.approx([0., 0., 0., 0., 0., .1])
    assert command['reference_filter_duration_s'] == pytest.approx(.1)
    assert result['pulses'][0]['motion']['yaw_change_deg'] == 0.


def test_archive_hash_mismatch_is_rejected_before_parsing(tmp_path):
    m = api()
    folder = tmp_path / 'run' / 'G1_YAW_P15'
    folder.mkdir(parents=True)
    archive = folder / 'episode.json.gz'
    archive.write_bytes(gzip.compress(json.dumps(episode()).encode()))
    receipt = dict(archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest())
    (folder / 'receipt.json').write_text(json.dumps(receipt))
    assert m.read_verified_archive(folder)[0]['outcome']['simulation_valid'] is True
    archive.write_bytes(b'changed')
    with pytest.raises(ValueError, match='hash'):
        m.read_verified_archive(folder)


def test_dropped_request_is_not_a_completed_pulse_and_missing_chain_is_visible():
    m = api()
    raw = episode()
    raw['transitions'][6]['action_log']['raw_action'] = [0.] * 5
    raw['transitions'][6]['action'] = [0.] * 5
    result = m.analyze_episode(raw, geometry=m.read_pin_geometry())
    assert result['pulses'][0]['status'] == 'interrupted'
    assert result['pulses'][0]['script_waveform_valid'] is False
    raw = episode()
    del raw['transitions'][4]['action_log']['pre_stage_total']
    result = m.analyze_episode(raw, geometry=m.read_pin_geometry())
    assert result['interface_recording_valid'] is False


def test_pulse_load_peaks_use_native_substep_maxima_and_keep_control_samples():
    m = api()
    raw = episode()
    raw['cycle_peaks'] = [dict(force_N=3., torque_G_Nm=.03) for _ in raw['transitions']]
    raw['cycle_peaks'][4] = dict(force_N=6., torque_G_Nm=.07)
    raw['cycle_peaks'][0] = dict(force_N=99., torque_G_Nm=9.)
    raw['cycle_peaks'][12] = dict(force_N=88., torque_G_Nm=8.)
    result = m.analyze_episode(raw, geometry=m.read_pin_geometry())
    motion = result['pulses'][0]['motion']
    assert motion['peak_force_N'] == 6.
    assert motion['peak_torque_Nm'] == .07
    assert motion['control_sample_peak_force_N'] == 2.
    assert motion['control_sample_peak_torque_M_Nm'] == .01
