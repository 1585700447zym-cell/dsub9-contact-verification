"""Reproducible prescribed-pose applicability diagnostics; never a control episode.

Original models, parameters and reports are read-only. Independent sampled pin
surface witnesses prove geometric overlap, not an exact maximum penetration or
hardware deformation. Distances are SI throughout the JSON.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import hashlib
import itertools
import json
import math
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

from tools.sdf.hole_reference import HoleParams
from tools.validation.run_contact_cases import (
    ROOT, FORMAL_MODEL, PLUGIN, MAX_PENETRATION_M, ContactCase, all_cases,
    _load_model, _quaternion, _male_world_wrench, _contact_wrench_on_body_world,
    contact_parameter_profiles,
)


def model_geometry():
    xml = ET.parse(FORMAL_MODEL).getroot()
    values = {c.get('key'): float(c.get('value'))
              for c in xml.findall('.//extension/plugin/instance/config')}
    params = HoleParams(**values)
    pins = []
    for g in xml.findall('.//geom'):
        if g.get('class') == 'pin_collision':
            radius, half_length = map(float, g.get('size').split())
            center = np.fromstring(g.get('pos'), sep=' ')
            hole = xml.find(f'.//geom[@name="hole_sdf_{g.get("name")[-2:]}"]')
            pins.append((g.get('name'), center, radius, half_length,
                         np.fromstring(hole.get('pos'), sep=' ')))
    return params, pins


DEFAULT_HOLE, PINS = model_geometry()


def material_distance(points, params):
    """Vectorized exact point distance to the revolved stepped material profile.

Membership uses explicit radial/axial intervals, independent of the plugin's
ray-crossing implementation. No contact solver is called here.
"""
    points = np.asarray(points, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all():
        raise ValueError('points must be a finite N by 3 array')
    r = np.hypot(points[:, 0], points[:, 1])
    z = points[:, 2]
    vertices = [(params.entry_radius, 0), (params.outer_radius, 0),
                (params.outer_radius, params.bore_depth),
                (params.bore_radius, params.bore_depth),
                (params.bore_radius, params.entry_depth),
                (params.entry_radius, params.entry_depth)]
    best = np.full(len(points), np.inf)
    for a, b in zip(vertices, vertices[1:] + vertices[:1]):
        dr, dz = b[0]-a[0], b[1]-a[1]
        t = np.clip(((r-a[0])*dr + (z-a[1])*dz)/(dr*dr+dz*dz), 0, 1)
        best = np.minimum(best, (r-a[0]-t*dr)**2+(z-a[1]-t*dz)**2)
    inside = ((r < params.outer_radius) & (z > 0) & (z < params.bore_depth)
              & (((z < params.entry_depth) & (r > params.entry_radius))
                 | ((z >= params.entry_depth) & (r > params.bore_radius))))
    return np.sqrt(best) * np.where(inside, -1, 1)


def rotation(case):
    matrix = np.zeros(9)
    mujoco.mju_quat2Mat(matrix, _quaternion(case))
    return matrix.reshape(3, 3)


def origin_for_pivot(nominal_origin, matrix, pivot_local):
    """Keep nominal world pivot fixed during rotation, then apply translation."""
    return np.asarray(nominal_origin) + pivot_local - matrix @ pivot_local


def geometry_witness(case, depth_m, angular_samples=360, axial_samples=161,
                     pivot_local=None):
    matrix = rotation(case)
    origin = np.array([case.x_offset_m, case.y_offset_m, case.start_origin_z_m+depth_m])
    if pivot_local is not None:
        origin = origin_for_pivot(origin, matrix, np.asarray(pivot_local))
    theta = np.arange(angular_samples) * (2*math.pi/angular_samples)
    results = []
    for name, center, radius, half_length, hole_center in PINS:
        angles, axial = np.meshgrid(theta, np.linspace(-half_length, half_length, axial_samples))
        shell = np.column_stack([radius*np.cos(angles.ravel()), radius*np.sin(angles.ravel()), axial.ravel()])
        angles, radial = np.meshgrid(theta, np.linspace(0, radius, 33))
        disk = np.column_stack([radial.ravel()*np.cos(angles.ravel()), radial.ravel()*np.sin(angles.ravel()),
                                np.full(angles.size, half_length)])
        bottom = disk.copy()
        bottom[:, 2] *= -1
        local = np.concatenate([shell, disk, bottom]) + center
        world = local @ matrix.T + origin
        in_hole = world - hole_center
        distance = material_distance(in_hole, DEFAULT_HOLE)
        index = int(np.argmin(distance))
        results.append({'pin': name, 'sampled_max_material_overlap_m': max(0., -float(distance[index])),
                        'point_in_hole_m': in_hole[index].tolist(),
                        'point_world_m': world[index].tolist(),
                        'point_male_local_m': local[index].tolist(),
                        'inside_sample_count': int(np.count_nonzero(distance < -1e-12))})
    results.sort(key=lambda row: row['sampled_max_material_overlap_m'], reverse=True)
    return {'case': case.name, 'depth_m': depth_m, 'angular_samples': angular_samples,
            'axial_samples': axial_samples, 'cap_radial_samples': 33,
            'pivot_local_m': None if pivot_local is None else list(pivot_local),
            'sampled_max_material_overlap_m': results[0]['sampled_max_material_overlap_m'],
            'deepest': results[0], 'pins': results,
            'scope': 'sampled pin surface versus corresponding analytic hole only; not D-shell clearance certification'}


def depth_grid(target, step):
    if not math.isfinite(step) or step <= 0 or not math.isfinite(target) or target < 0:
        raise ValueError('invalid scan target or spatial step')
    return [min(i*step, target) for i in range(math.ceil(target/step)+1)]


def contact_records(model, data, male):
    rows = []
    for i in range(data.ncon):
        c = data.contact[i]
        body1, body2 = (int(model.geom_bodyid[g]) for g in (c.geom1, c.geom2))
        if male not in (body1, body2):
            continue
        f = np.zeros(6)
        mujoco.mj_contactForce(model, data, i, f)
        wrench = _contact_wrench_on_body_world(c.frame, f, c.pos, data.xpos[male],
                                             body_is_geom2=body2 == male)
        rows.append({'pair': [mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, int(g))
                              for g in (c.geom1, c.geom2)],
                     'dist_m': float(c.dist), 'penetration_m': max(0., -float(c.dist)),
                     'position_world_m': np.asarray(c.pos).tolist(),
                     'normal_geom1_to_geom2_world': np.asarray(c.frame).reshape(3, 3)[0].tolist(),
                     'wrench_on_male_about_mate_world': wrench.tolist()})
    rows.sort(key=lambda r: r['penetration_m'], reverse=True)
    return rows


def scan(case, step_m=1e-5, profile='baseline', mode='sdf', pivot_local=None):
    model = _load_model(mode, .0002, profile)
    data = mujoco.MjData(model)
    male = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, 'male')
    samples, events = [], {}
    max_penetration = 0.
    termination = 'SCAN_TARGET_REACHED'
    for depth in depth_grid(case.target_depth_m, step_m):
        origin = np.array([case.x_offset_m, case.y_offset_m, case.start_origin_z_m+depth])
        if pivot_local is not None:
            origin = origin_for_pivot(origin, rotation(case), np.asarray(pivot_local))
        data.qpos[:7] = (*origin, *_quaternion(case))
        data.qvel[:] = 0
        data.qacc_warmstart[:] = 0
        mujoco.mj_forward(model, data)
        wrench, penetration = _male_world_wrench(model, data, male)
        if not (np.isfinite(wrench).all() and np.isfinite(data.qpos).all()
                and np.isfinite(data.qfrc_constraint).all() and math.isfinite(penetration)
                and all(math.isfinite(float(data.contact[i].dist)) for i in range(data.ncon))):
            raise FloatingPointError(f'nonfinite state: {case.name} at {depth}')
        row = {'depth_m': depth, 'male_origin_world_m': origin.tolist(), 'wrench': wrench.tolist(),
               'contact_count': data.ncon, 'penetration_m': penetration}
        samples.append(row)
        snapshot = None
        if data.ncon and 'first_contact' not in events:
            snapshot = dict(row, contacts=contact_records(model, data, male))
            events['first_contact'] = snapshot
        if penetration >= max_penetration and data.ncon:
            snapshot = snapshot or dict(row, contacts=contact_records(model, data, male))
            events['peak_penetration'] = snapshot
        max_penetration = max(max_penetration, penetration)
        if penetration > MAX_PENETRATION_M:
            events['first_exceed'] = snapshot or dict(row, contacts=contact_records(model, data, male))
            events['previous_to_exceed'] = previous_snapshot if len(samples) > 1 else None
            termination = 'EXCESS_PENETRATION'
            break
        previous_snapshot = dict(row, contacts=contact_records(model, data, male)) if data.ncon else dict(row, contacts=[])
    return {'case': asdict(case), 'step_m': step_m, 'timestep_s': .0002, 'profile': profile,
            'mode': mode, 'pivot_local_m': None if pivot_local is None else list(pivot_local),
            'termination': termination, 'final_depth_m': samples[-1]['depth_m'],
            'max_penetration_m': max_penetration, 'samples': samples, 'events': events}


def experiment_cases():
    cases = list(all_cases())
    for c in (ContactCase.combined(), ContactCase.combined_b()):
        for scale in (.25, .5, .75):
            cases.append(replace(c, name=f'{c.name}_scale_{scale:g}', x_offset_m=c.x_offset_m*scale,
                                 y_offset_m=c.y_offset_m*scale, roll_rad=c.roll_rad*scale, pitch_rad=c.pitch_rad*scale))
        cases.append(replace(c, name=c.name+'_translation_only', roll_rad=0, pitch_rad=0))
        cases.append(replace(c, name=c.name+'_rotation_only', x_offset_m=0, y_offset_m=0))
        for field in ('x_offset_m', 'y_offset_m', 'roll_rad', 'pitch_rad'):
            cases.append(replace(c, name=c.name+'_without_'+field, **{field: 0}))
    for i, signs in enumerate(itertools.product((-1, 1), repeat=4)):
        cases.append(ContactCase(f'dev_corner_{i:02}', signs[0]*25e-6, signs[1]*25e-6,
                                 signs[2]*math.radians(.5), signs[3]*math.radians(.5), -.004, .004))
    rng = np.random.default_rng(20260914)
    for i, v in enumerate(rng.uniform(-1, 1, (16, 4))):
        cases.append(ContactCase(f'dev_random_{i:02}', v[0]*25e-6, v[1]*25e-6,
                                 v[2]*math.radians(.5), v[3]*math.radians(.5), -.004, .004))
    return cases


def fingerprint():
    paths = [FORMAL_MODEL, PLUGIN, ROOT/'reports/contact_validation_results.json',
             ROOT/'reports/v1_contact_traces.json', ROOT/'tools/validation/run_contact_cases.py',
             ROOT/'tools/sdf/hole_reference.py', ROOT/'plugins/dsub9_hole_sdf/hole_sdf.cc',
             ROOT/'tools/model/generate_mjcf.py', Path(__file__)]
    for directory in ('models', 'assets', 'plugins/dsub9_hole_sdf', 'deliverables/v1_applicability/inputs'):
        paths.extend(p for p in (ROOT/directory).rglob('*') if p.is_file())
    return {str(p.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(set(paths))}


def validate_output(path):
    path = Path(path).resolve()
    allowed = (ROOT/'deliverables/v1_applicability').resolve()
    if path.parent != allowed or path.suffix.lower() != '.json':
        raise ValueError('output must be a JSON directly inside deliverables/v1_applicability')
    return path


def audit_pose(case, depth_m, initpoints=40, iterations=10):
    """Cross-check geometric witnesses with detected contacts at the SAME pose.

Increasing SDF search effort is a diagnostic intervention, not a validated fix.
Cached model settings are always restored before returning.
"""
    witness = geometry_witness(case, depth_m, angular_samples=180, axial_samples=81)
    model = _load_model('sdf', .0002, 'baseline')
    original = (model.opt.sdf_initpoints, model.opt.sdf_iterations)
    try:
        model.opt.sdf_initpoints, model.opt.sdf_iterations = initpoints, iterations
        data = mujoco.MjData(model)
        data.qpos[:7] = (case.x_offset_m, case.y_offset_m, case.start_origin_z_m+depth_m, *_quaternion(case))
        mujoco.mj_forward(model, data)
        male = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, 'male')
        contacts = contact_records(model, data, male)
        overlap_pins = [p['pin'] for p in witness['pins'] if p['sampled_max_material_overlap_m'] > 1e-6]
        pairs = {tuple(c['pair']) for c in contacts}
        missing = [[pin, 'hole_sdf_'+pin[-2:]] for pin in overlap_pins
                   if (pin, 'hole_sdf_'+pin[-2:]) not in pairs and ('hole_sdf_'+pin[-2:], pin) not in pairs]
        return {'case': asdict(case), 'depth_m': depth_m, 'sdf_initpoints': initpoints,
                'sdf_iterations': iterations, 'contact_count': data.ncon,
                'contacts': contacts, 'geometry_witness': witness,
                'witness_reporting_threshold_m': 1e-6, 'missing_overlap_pairs': missing,
                'meaning': 'missing pair proves a detected coverage defect; empty list does not certify complete contact coverage'}
    finally:
        model.opt.sdf_initpoints, model.opt.sdf_iterations = original


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'deliverables/v1_applicability/diagnostic_results.json')
    args = parser.parse_args()
    try:
        args.output = validate_output(args.output)
    except ValueError as exc:
        parser.error(str(exc))
    before = fingerprint()
    cases = experiment_cases()
    scans = []
    for case in cases:
        result = scan(case)
        scans.append(result)
        print(f'{case.name}: {result["termination"]}, depth={result["final_depth_m"]*1000:.3f} mm, '
              f'penetration={result["max_penetration_m"]*1e6:.3f} um', flush=True)
    sensitivity = []
    for c in (ContactCase.combined(), ContactCase.combined_b()):
        for step in (5e-6, 2e-6):
            sensitivity.append(scan(c, step_m=step))
        for profile in ('low_response', 'high_response'):
            sensitivity.append(scan(c, profile=profile))
        sensitivity.append(scan(c, pivot_local=[0., 0., -.0145]))
    witnesses = []
    for result in scans:
        if result['case']['name'] in ('combined_a', 'combined_b', 'aligned'):
            case = ContactCase(**result['case'])
            for tag in ('first_contact', 'previous_to_exceed', 'first_exceed'):
                if result['events'].get(tag):
                    event = result['events'][tag]
                    w = geometry_witness(case, event['depth_m'])
                    w['event'] = tag
                    witnesses.append(w)
            if case.name == 'aligned':
                w = geometry_witness(case, .004)
                w['event'] = 'full_depth'
                witnesses.append(w)
    # Resolution check on the same physical poses, not on different depth grids.
    for case, depth in ((ContactCase.combined(), .00018), (ContactCase.combined_b(), .00026)):
        w = geometry_witness(case, depth, angular_samples=720, axial_samples=321)
        w['event'] = 'surface_sampling_refinement'
        witnesses.append(w)
    coverage = []
    for c in cases:
        if c.name.startswith('dev_') or c.name in ('aligned', 'roll_pos_1.5deg', 'pitch_pos_1.5deg'):
            for depth in (.0005, .001, .002, .004):
                coverage.append(audit_pose(c, depth))
    search_sensitivity = []
    for c in cases:
        if c.name in ('roll_pos_1.5deg', 'pitch_pos_1.5deg', 'dev_corner_02', 'dev_corner_04',
                      'dev_corner_11', 'dev_corner_13'):
            for initpoints, iterations in ((40, 10), (40, 50), (200, 10), (200, 50), (1000, 10)):
                search_sensitivity.append(audit_pose(c, .004, initpoints, iterations))
    if before != fingerprint():
        raise RuntimeError('source files changed during diagnosis')
    result = {'schema_version': 1, 'scope': 'prescribed_pose_quasistatic_diagnostic_not_dynamic_validation',
              'git_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'python': sys.version, 'mujoco_version': mujoco.__version__, 'source_sha256': before,
              'numerical_penetration_limit_m': MAX_PENETRATION_M,
              'geometry': {'hole': asdict(DEFAULT_HOLE), 'grasp_frame_status': 'nominal_not_calibrated'},
              'effective_contact_profiles': {k: asdict(v) for k, v in contact_parameter_profiles().items()},
              'baseline_sdf_search': {'initpoints': 40, 'iterations': 10},
              'dev_sampling': {'seed': 20260914, 'translation_each_axis_m': 25e-6,
                               'roll_pitch_each_rad': math.radians(.5), 'corners': 16, 'random_points': 16,
                               'claim': 'finite sampled set only, not a certified continuous domain'},
              'scans': scans, 'sensitivity': sensitivity, 'geometry_witnesses': witnesses,
              'coverage_audit': coverage, 'search_sensitivity': search_sensitivity,
              'applicability': 'NOT_READY_FOR_CONTACT_CONTROL' if any(a['missing_overlap_pairs'] for a in coverage)
                               else 'NO_COVERAGE_DEFECT_FOUND_IN_SAMPLED_POSES_NOT_DYNAMIC_VALIDATION'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8', newline='\n')
    print(f'Wrote {args.output}; {len(scans)} main scans and {len(sensitivity)} sensitivity scans', flush=True)


if __name__ == '__main__':
    main()
