"""Coverage gate for a separate convex development model, not a control episode."""
from dataclasses import asdict
import hashlib
import json
import math
import re
import time

import mujoco
import numpy as np

from tools.model.contact_development import OUTPUT_DIR, load_model, export_model, radial_error
from tools.validation.diagnose_v1_applicability import (
    DEFAULT_HOLE, PINS, material_distance, rotation, experiment_cases, fingerprint,
)
from tools.validation.run_contact_cases import (
    ROOT, ContactCase, _load_model, _quaternion, _male_world_wrench, _project_root_cwd,
)


def fast_witness(case, depth_m):
    """Positive samples prove overlap; absence of samples is not a clearance proof."""
    theta = np.arange(48)*2*np.pi/48
    a, z = np.meshgrid(theta, np.linspace(-1, 1, 33))
    shell = np.column_stack((np.cos(a.ravel()), np.sin(a.ravel()), z.ravel()))
    a, r = np.meshgrid(theta, np.linspace(0, 1, 9))
    cap = np.column_stack((r.ravel()*np.cos(a.ravel()), r.ravel()*np.sin(a.ravel()), np.ones(a.size)))
    bottom = cap.copy(); bottom[:, 2] = -1
    unit = np.concatenate((shell, cap, bottom))
    local = np.array([unit*np.array([radius, radius, half])+center
                      for _, center, radius, half, _ in PINS])
    origin = [case.x_offset_m, case.y_offset_m, case.start_origin_z_m+depth_m]
    points = local @ rotation(case).T + origin - np.array([p[4] for p in PINS])[:, None, :]
    distances = material_distance(points.reshape(-1, 3), DEFAULT_HOLE).reshape(9, -1)
    return {'pins': [{'pin': p[0], 'sampled_max_material_overlap_m': max(0., -float(d.min()))}
                     for p, d in zip(PINS, distances)]}


def hole_number(name):
    match = re.fullmatch(r'hole_sdf_(\d+)', name)
    if not match:
        match = re.match(r'hole_(?:convex\d+_|fallback_\d+_h)(\d+)_', name)
    return match.group(1) if match else None


def check_pose(model, case, depth_m, witness):
    data = mujoco.MjData(model)
    data.qpos[:7] = (case.x_offset_m, case.y_offset_m,
                     case.start_origin_z_m+depth_m, *_quaternion(case))
    expected = sorted(p['pin'] for p in witness['pins'] if p['sampled_max_material_overlap_m'] > 1e-6)
    row = {'case': case.name, 'depth_m': float(depth_m), 'expected_pins': expected}
    try:
        mujoco.mj_forward(model, data)
        detected = set()
        for contact in data.contact:
            names = [mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, int(g)) or ''
                     for g in (contact.geom1, contact.geom2)]
            for pin, hole in (names, names[::-1]):
                if pin.startswith('pin_') and hole_number(hole) == pin[-2:]:
                    detected.add(pin)
        male = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, 'male')
        wrench, penetration = _male_world_wrench(model, data, male)
        finite = bool(np.isfinite(wrench).all() and np.isfinite(data.qacc).all()
                      and np.isfinite(data.qfrc_constraint).all()
                      and all(np.isfinite(c.frame).all() and math.isfinite(c.dist) for c in data.contact))
        row.update(status='OK' if finite else 'NONFINITE', finite=finite,
                   missing_pins=sorted(set(expected)-detected), detected_pins=sorted(detected),
                   contact_count=data.ncon, max_penetration_m=penetration, wrench=wrench.tolist())
    except mujoco.FatalError as error:
        row.update(status='SIMULATION_ERROR', error=str(error), finite=False,
                   missing_pins=expected, detected_pins=[], contact_count=None,
                   max_penetration_m=None, wrench=None)
    return row


def summarize(rows):
    return {'poses': len(rows), 'missing_poses': sum(bool(r['missing_pins']) for r in rows),
            'poses_with_witness_overlap': sum(bool(r['expected_pins']) for r in rows),
            'poses_with_contacts': sum(bool(r['contact_count']) for r in rows),
            'missing_pairs': sum(len(r['missing_pins']) for r in rows),
            'simulation_errors': sum(r['status']=='SIMULATION_ERROR' for r in rows),
            'nonfinite_poses': sum(r['status']=='NONFINITE' for r in rows),
            'max_contacts': max((r['contact_count'] or 0) for r in rows),
            'gate_pass': all(r['status']=='OK' and not r['missing_pins'] for r in rows)}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n',
                    encoding='utf-8', newline='\n')


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    before = fingerprint()
    current_paths = ['tools/model/contact_development.py', 'tools/validation/repair_contact_coverage.py',
                     'tests/contact/test_contact_development.py', 'deliverables/v1_applicability/diagnostic_results.json']
    current_hashes = {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in current_paths}
    old = json.loads((ROOT/'deliverables/v1_applicability/diagnostic_results.json').read_text(encoding='utf-8'))
    if before != old['source_sha256']:
        raise RuntimeError('Historical diagnostic sources have changed')
    path = export_model()
    with _project_root_cwd():
        exported = mujoco.MjModel.from_xml_path(path.relative_to(ROOT).as_posix())
    variants = {}; timings = {}
    for label in ('sdf40', 'sdf200', 'sdf500', 'sdf1000', 'polygon32_original', 'convex64', 'convex128', 'convex256'):
        if label.startswith('sdf'):
            model = _load_model('sdf', .0002); model.opt.sdf_initpoints = int(label[3:])
        elif label == 'polygon32_original':
            model = _load_model('polygon32', .0002)
        else:
            model = exported if label == 'convex128' else load_model(int(label[6:]))
        rows = []; start = time.perf_counter()
        for item in old['coverage_audit']:
            rows.append(check_pose(model, ContactCase(**item['case']), item['depth_m'], item['geometry_witness']))
        timings[label] = {'seconds_140_pose_checks': time.perf_counter()-start,
                          'includes_data_allocation_and_force_extraction': True, 'excludes_compilation': True}
        options = {key: getattr(model.opt, key) for key in
                   ('timestep','ccd_tolerance','ccd_iterations','sdf_initpoints','sdf_iterations','iterations','tolerance')}
        variants[label] = {'summary': summarize(rows), 'effective_options': options, 'rows': rows}
        print(label, variants[label]['summary'], flush=True)
    _load_model('sdf', .0002).opt.sdf_initpoints = 40
    cases = experiment_cases()
    rng = np.random.default_rng(20260915)
    for i, v in enumerate(rng.uniform(-1, 1, (32, 4))):
        cases.append(ContactCase(f'coverage_holdout_{i:02}', v[0]*25e-6, v[1]*25e-6,
                                 v[2]*math.radians(.5), v[3]*math.radians(.5), -.004, .004))
    dense = []; start = time.perf_counter()
    for case in cases:
        # 50 um throughout; 10 um near the mouth, using integer micrometres.
        depths = sorted(set(range(0, 4001, 50)) | set(range(0, 501, 10))) if case.target_depth_m else [0]
        for depth_um in depths:
            depth = depth_um*1e-6
            witness = fast_witness(case, depth)
            row = check_pose(exported, case, depth, witness)
            row['sampled_overlap_m'] = {p['pin']: p['sampled_max_material_overlap_m'] for p in witness['pins']}
            dense.append(row)
        print(case.name, summarize(dense[-len(depths):]), flush=True)
    timings['dense_scan_seconds_including_witness'] = time.perf_counter()-start
    after = fingerprint()
    if before != after:
        raise RuntimeError('Historical sources changed during validation')
    if current_hashes != {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in current_paths}:
        raise RuntimeError('Current validation inputs changed during validation')
    selected = variants['convex128']['summary']['gate_pass'] and summarize(dense)['gate_pass']
    result = {'schema_version': 1, 'scope': 'prescribed_pose_contact_coverage_not_dynamic_or_physical_validation',
              'mujoco_version': mujoco.__version__, 'verdict': 'COVERAGE_GATE_PASS' if selected else 'COVERAGE_GATE_FAIL',
              'selected_model': path.name, 'model_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
              'historical_sources_unchanged': before == after, 'historical_source_sha256': before,
              'current_input_sha256': current_hashes,
              'reporting_overlap_threshold_m': 1e-6, 'witness_sampling': {'angles':48,'axial':33,'cap_radial':9},
              'radial_error_m': {str(n): {'bore': radial_error(.000575,n), 'entry':radial_error(.000675,n)} for n in (32,64,128,256)},
              'variants': variants, 'dense_cases': [asdict(c) for c in cases],
              'dense_summary': summarize(dense), 'dense_rows': dense}
    write_json(OUTPUT_DIR/'coverage_results.json', result)
    write_json(OUTPUT_DIR/'timing.json', timings)
    print(result['verdict'], result['dense_summary'], flush=True)


if __name__ == '__main__':
    main()
