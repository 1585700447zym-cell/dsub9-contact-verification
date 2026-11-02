"""Bounded B1 configuration review; preserve the historical dynamic matrix.

Exactly two extended STOPPING episodes use the unchanged CartesianEnvironment.
Frozen-pose comparisons are fresh forward solves, not additional trajectories.
"""
from __future__ import annotations

import copy
import hashlib
import json
import time

import mujoco
import numpy as np

from tools.dynamics.cartesian import CartesianEnvironment, DynamicConfig
from tools.dynamics.safety import shift_wrench
from tools.validation.diagnose_v1_applicability import fingerprint
from tools.validation.run_contact_cases import ROOT, ContactCase, _male_world_wrench

OLD = ROOT / 'deliverables/dynamic_actuator_v1'
OUTPUT = ROOT / 'deliverables/b1_fixed_admittance/configuration_review.json'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def dump(value):
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n',
                      encoding='utf-8', newline='\n')


def protected_hashes():
    paths = list(OLD.rglob('*'))
    paths += [ROOT / p for p in ('tools/dynamics/cartesian.py', 'tools/dynamics/safety.py',
                                'tools/model/contact_development.py')]
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in paths if p.is_file()}


def pose_query(env, source):
    """Same qpos, qvel and world-axis external wrench; zero initial warm start."""
    model = env.model
    data = mujoco.MjData(model)
    qpos = np.r_[source['position_m'], source['quaternion_wxyz']]
    data.qpos[:] = qpos
    rotation = np.zeros(9)
    mujoco.mju_quat2Mat(rotation, qpos[3:])
    rotation = rotation.reshape(3, 3)
    data.qvel[:] = np.r_[source['velocity_world'][:3], rotation.T @ source['velocity_world'][3:]]
    # Populate kinematics required by mj_applyFT, then clear solver warm start.
    mujoco.mj_forward(model, data)
    at_m = np.asarray(source['drive_wrench_M'])
    p = data.xpos[env.male].copy()
    g = p + rotation @ env.grasp_local
    at_g = shift_wrench(at_m, p, g)
    data.qfrc_applied[:] = 0
    mujoco.mj_applyFT(model, data, at_g[:3], at_g[3:], g, env.male, data.qfrc_applied)
    data.qacc_warmstart[:] = 0
    mujoco.mj_forward(model, data)
    wrench, depth = _male_world_wrench(model, data, env.male)
    fast = np.r_[data.qfrc_constraint[:3], rotation @ data.qfrc_constraint[3:]]
    contact = min(data.contact, key=lambda c: c.dist) if data.ncon else None
    return {
        'segments': env.segments, 'effective_options': env.metadata()['effective_options'],
        'qpos': data.qpos.tolist(), 'qvel': data.qvel.tolist(),
        'applied_world_wrench_M': at_m.tolist(), 'applied_world_wrench_G': at_g.tolist(),
        'qfrc_applied': data.qfrc_applied.tolist(),
        'contact_wrench_M': wrench.tolist(), 'contact_wrench_G': shift_wrench(wrench, p, g).tolist(),
        'force_N': float(np.linalg.norm(wrench[:3])),
        'torque_G_Nm': float(np.linalg.norm(shift_wrench(wrench, p, g)[3:])),
        'contact_count': int(data.ncon), 'max_penetration_m': depth,
        'most_negative_contact': None if contact is None else {
            'geom_pair': [mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, int(k))
                          for k in (contact.geom1, contact.geom2)],
            'dist_m': float(contact.dist), 'position_world_m': contact.pos.tolist(),
            'normal_geom1_to_geom2_world': contact.frame[:3].tolist()},
        'direct_contact_sum_matches_generalized_constraint_wrench': bool(np.allclose(wrench, fast, rtol=0, atol=1e-10)),
        'max_wrench_crosscheck_error': float(np.max(np.abs(wrench-fast))),
        'finite': bool(all(np.isfinite(x).all() for x in (data.qpos, data.qvel, data.qacc,
                         data.qfrc_constraint, data.contact.dist, wrench))),
        'warning_counts': [int(w.number) for w in data.warning],
        'qpos_unchanged': bool(np.array_equal(data.qpos, qpos)),
        'simulation_time_s': float(data.time),
    }


def divergence_review(runs128, runs256):
    a = next(r for r in runs128 if r['name']=='combined_a_scale_0.5')
    b = next(r for r in runs256 if r['name']==a['name'])
    other = {round(r['time_s'], 9): r for r in b['trace']}
    pairs = [(r, other[round(r['time_s'], 9)]) for r in a['trace']
             if r['time_s'] <= 1.2+1e-9 and round(r['time_s'], 9) in other]
    differences = [float(np.linalg.norm(np.asarray(r['position_m'])-s['position_m'])) for r, s in pairs]
    first = next(i for i, d in enumerate(differences) if d > 1e-6)
    envs = [CartesianEnvironment(DynamicConfig(), n) for n in (128, 256)]
    fixtures = []
    for i in (first-1, first, first+1):
        source, other_row = pairs[i]
        queries = [pose_query(env, source) for env in envs]
        assert queries[0]['qpos'] == queries[1]['qpos']
        assert queries[0]['qvel'] == queries[1]['qvel']
        assert np.allclose(queries[0]['qfrc_applied'], queries[1]['qfrc_applied'], rtol=0, atol=1e-15)
        assert all(q['finite'] and q['qpos_unchanged'] and q['simulation_time_s']==0
                   and q['direct_contact_sum_matches_generalized_constraint_wrench'] for q in queries)
        fixtures.append({'source_resolution': 128, 'source_time_s': source['time_s'],
                         'saved_position_difference_m': differences[i],
                         'source_saved_row': source, 'other_resolution_saved_row': other_row,
                         'queries': queries})
    return {
        'case': a['name'], 'position_difference_threshold_m': 1e-6,
        'logged_sample_period_s': .002, 'first_above_threshold_s': pairs[first][0]['time_s'],
        'first_position_difference_m': differences[first],
        'preceding_sample_s': pairs[first-1][0]['time_s'],
        'preceding_position_difference_m': differences[first-1],
        'first_contact_128': a['first_contact'], 'first_contact_256': b['first_contact'],
        'fixtures': fixtures,
        'interpretation': 'First crossing is resolved only to the saved 2 ms sampling. Frozen comparisons use the same 128-source physical pose, qvel and external wrench with a fresh zero-warm-start forward solve. They isolate geometry/contact response sensitivity; neither resolution is established as physical truth.',
        'wrench_convention': 'All components use world axes. M is the male body origin/COM; G = M + R*[0,0,-0.0145] m. tau_G = tau_M + (M-G) cross F. Free-joint angular qvel is body-local.',
    }


def metrics(row, stop_position):
    return {'time_s': row['time_s'], 'position_m': row['position_m'],
            'speed_m_s': float(np.linalg.norm(row['velocity_world'][:3])),
            'angular_speed_rad_s': float(np.linalg.norm(row['velocity_world'][3:])),
            'force_N': float(np.linalg.norm(row['contact_wrench_M'][:3])),
            'torque_G_Nm': float(np.linalg.norm(row['contact_wrench_G'][3:])),
            'drift_from_stop_m': float(np.linalg.norm(np.asarray(row['position_m'])-stop_position)),
            'penetration_m': row['penetration_m'], 'phase': row['phase']}


def extended_stop(saved):
    env = CartesianEnvironment(DynamicConfig(), 128)
    env.reset(ContactCase(**saved['case']))
    start = time.perf_counter()
    trace = [env.observe()]
    for _ in range(round(1.2/env.config.control_period)):
        trace.append(env.step([0, 0, .001, 0, 0, 0]))
        if env.phase in ('STOPPING', 'TERMINAL'):
            break
    end_drive = env.observe()
    assert np.allclose(end_drive['position_m'], saved['end_drive']['position_m'], rtol=0, atol=1e-12)
    if env.phase == 'RUNNING':
        env.stop('DRIVE_WINDOW_ENDED')
    if env.phase != 'STOPPING':
        raise RuntimeError('Unexpected terminal state before extended stopping')
    stop_time = env.data.time
    stop_position = env.data.qpos[:3].copy()
    stop_peaks = {'force_N': 0., 'torque_G_Nm': 0., 'penetration_m': 0., 'speed_m_s': 0.}
    checkpoints = []
    live_finite = True
    # Observe every physical step for peak loads and finiteness without altering dynamics.
    # Existing _record_peaks is called by the unchanged environment each physics step.
    original_record = env._record_peaks
    def record(row):
        nonlocal live_finite
        original_record(row)
        live_finite = live_finite and env._state_valid()
        for key, value in [('force_N', np.linalg.norm(row['contact_wrench_M'][:3])),
                           ('torque_G_Nm', np.linalg.norm(row['contact_wrench_G'][3:])),
                           ('penetration_m', row['penetration_m']),
                           ('speed_m_s', np.linalg.norm(row['velocity_world'][:3]))]:
            stop_peaks[key] = max(stop_peaks[key], float(value))
    env._record_peaks = record
    stopping = [env.observe()]
    for i in range(1, round(2./env.config.control_period)+1):
        row = env.step(np.zeros(6))
        trace.append(row)
        stopping.append(row)
        if i in (100, 250, 500, 1000):
            checkpoints.append(dict(metrics(row, stop_position), relative_stop_time_s=i*env.config.control_period,
                                    stop_window_peak_so_far=copy.deepcopy(stop_peaks),
                                    whole_episode_peak_so_far=copy.deepcopy(env.peaks)))
        if env.phase == 'TERMINAL':
            break
    positions = np.array([r['position_m'] for r in stopping])
    speeds = np.array([np.linalg.norm(r['velocity_world'][:3]) for r in stopping])
    angular_speeds = np.array([np.linalg.norm(r['velocity_world'][3:]) for r in stopping])
    below = (speeds < env.config.stopped_speed) & (angular_speeds < env.config.stopped_angular_speed)
    stays_below = np.logical_and.accumulate(below[::-1])[::-1]
    settling = next((r['time_s']-stop_time for r, yes in zip(stopping, stays_below) if yes), None)
    return {'name': saved['name'], 'metadata': env.metadata(), 'case': saved['case'],
            'drive_duration_requested_s': 1.2, 'stopping_duration_requested_s': 2.,
            'stop_time_s': stop_time, 'stopping_duration_actual_s': env.data.time-stop_time,
            'end_drive': end_drive, 'stop_snapshot': env.stop_snapshot, 'checkpoints': checkpoints,
            'final': env.observe(), 'events': env.events, 'recovery_requested': False,
            'stop_window_peaks': stop_peaks, 'whole_episode_peaks': env.peaks,
            'net_drift_from_stop_m': float(np.linalg.norm(positions[-1]-stop_position)),
            'maximum_drift_from_stop_m': float(np.max(np.linalg.norm(positions-stop_position, axis=1))),
            'sampled_stopping_path_length_m': float(np.sum(np.linalg.norm(np.diff(positions, axis=0), axis=1))),
            'speed_below_both_limits_through_remaining_observed_window_from_s': settling,
            'settling_scope': 'At 2 ms trace samples through the finite 2 s observation window; no infinite-time stability claim.',
            'finite_every_physics_step': bool(live_finite and env._state_valid()),
            'warning_counts': [int(w.number) for w in env.data.warning],
            'physical_steps': env.physical_steps, 'trace': trace,
            'wall_seconds': time.perf_counter()-start,
            'historical_push_endpoint_reproduced_within_m': 1e-12}


def main():
    protected = protected_hashes()
    history = fingerprint()
    runs128 = read(OLD/'n128_dt0.0002.json')['runs']
    runs256 = read(OLD/'n256_dt0.0002.json')['runs']
    task1 = divergence_review(runs128, runs256)
    previous = read(OLD/'dynamic_results.json')['summary']
    stops256 = [{'name': r['name'],
                 'stop_speed_m_s': float(np.linalg.norm(r['stop_check_0p2']['velocity_world'][:3])),
                 'pass_old_linear_stop_gate': bool(np.linalg.norm(r['stop_check_0p2']['velocity_world'][:3])<1e-5)}
                for r in runs256]
    result = {'schema_version': 1, 'status': 'TASK1_COMPLETE_TASK2_PENDING',
              'mujoco_version': mujoco.__version__, 'historical_source_sha256': history,
              'protected_input_sha256': protected, 'task1_frozen_pose_divergence': task1,
              'task2_extended_stopping': [],
              'candidate_review': {
                  'first_B1_development_candidate': {'segments': 256, 'timestep_s': .0002, 'collision_backend': 'mpr'},
                  'historical_n256_stop_checks': stops256,
                  'all_seven_n256_pass_old_linear_stop_gate': all(r['pass_old_linear_stop_gate'] for r in stops256),
                  'historical_global_dynamic_gate': previous['verdict'],
                  'historical_global_gates': previous['gates'],
                  'decision_scope': '256 / 0.0002 s MPR is a reasonable first bounded B1 development candidate because all seven stored 256 runs pass the old 0.2 s linear stop check. This does not establish resolution convergence, calibrated contact forces, full-domain reliability, or physical truth. Half-A/B sensitivity remains explicit.'}}
    dump(result)
    print('TASK1_COMPLETE', json.dumps({'time_s': task1['first_above_threshold_s'],
          'fixtures': [{'time_s': f['source_time_s'], 'queries': [{k: q[k] for k in
           ('segments', 'contact_count', 'max_penetration_m', 'force_N', 'most_negative_contact')} for q in f['queries']]}
          for f in task1['fixtures']]}, ensure_ascii=False), flush=True)
    for name in ('combined_a_scale_0.5', 'combined_b_scale_0.5'):
        row = extended_stop(next(r for r in runs128 if r['name']==name))
        result['task2_extended_stopping'].append(row)
        dump(result)
        print('TASK2_EPISODE_COMPLETE', name, json.dumps({'checkpoints': row['checkpoints'],
              'net_drift_m': row['net_drift_from_stop_m'], 'finite': row['finite_every_physics_step'],
              'settling_s': row['speed_below_both_limits_through_remaining_observed_window_from_s']}, ensure_ascii=False), flush=True)
    result['protected_inputs_unchanged'] = protected == protected_hashes()
    result['historical_sources_unchanged'] = history == fingerprint()
    assert result['protected_inputs_unchanged'] and result['historical_sources_unchanged']
    result['status'] = 'COMPLETE'
    dump(result)
    print('COMPLETE', str(OUTPUT), flush=True)


if __name__ == '__main__':
    main()
