"""Reproduce one frozen grazing pose; static diagnostics, never a baseline change."""
import argparse
import copy
import json
import mujoco
import numpy as np
from tools.dynamics.cartesian import CartesianEnvironment
from tools.validation.run_b2_search import read_run
from tools.validation.validate_training_readiness import ROOT, sha, verify_hashes, new_target

OUT = ROOT / 'deliverables/stop_reliability'


def evaluate(model, row, shift_z=0.):
    data = mujoco.MjData(model)
    data.qpos[:] = row['position_m'] + row['quaternion_wxyz']
    data.qpos[2] += shift_z
    mujoco.mj_forward(model, data)
    pin = model.geom('pin_07').id
    rot = data.geom_xmat[pin].reshape(3, 3)
    highest = float(data.geom_xpos[pin, 2] + model.geom_size[pin, 1]*abs(rot[2, 2])
                    + model.geom_size[pin, 0]*np.linalg.norm(rot[2, :2]))
    records = []
    for c in data.contact:
        pair = [int(c.geom1), int(c.geom2)]
        if pin not in pair:
            continue
        hole = pair[1] if pair[0] == pin else pair[0]
        name = model.geom(hole).name
        if not name.startswith('hole_convex256_07_main_'):
            continue
        mesh = model.geom_dataid[hole]
        first = model.mesh_vertadr[mesh]
        vertices = model.mesh_vert[first:first+model.mesh_vertnum[mesh]].astype(float)
        world = vertices @ data.geom_xmat[hole].reshape(3, 3).T + data.geom_xpos[hole]
        lowest = float(world[:, 2].min())
        records.append(dict(hole=name, depth_m=float(-c.dist), normal=c.frame[:3].tolist(),
                            margin=float(c.includemargin), cylinder_max_z_m=highest,
                            mesh_min_z_m=lowest, signed_axial_overlap_m=highest-lowest,
                            axial_separation_upper_bound_m=max(0., highest-lowest)))
    return dict(contact_count=int(data.ncon),
                max_penetration_m=max(0., -float(min(data.contact.dist))) if data.ncon else 0.,
                pair_contacts=records, ccd_tolerance=model.opt.ccd_tolerance,
                ccd_iterations=model.opt.ccd_iterations, disableflags=int(model.opt.disableflags))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    args = parser.parse_args()
    target = new_target(OUT, args.tag)
    prior = OUT/'diagnosis_v1'
    index = json.loads((prior/'results_index.json').read_text(encoding='utf-8'))
    verify_hashes(prior, index['files'])
    verify_hashes(ROOT, index['source_sha256'])
    run = read_run(prior/'baseline_0p2ms.json.gz')
    row = run['trace'][20]
    model = CartesianEnvironment(segments=256).model
    results = {}
    for name in ('original_mpr', 'single_contact_mpr', 'tolerance_1e12', 'iterations_350', 'native_ccd'):
        m = copy.deepcopy(model)
        if name == 'single_contact_mpr':
            m.opt.disableflags |= int(mujoco.mjtDisableBit.mjDSBL_MULTICCD)
        elif name == 'tolerance_1e12':
            m.opt.ccd_tolerance = 1e-12
        elif name == 'iterations_350':
            m.opt.ccd_iterations = 350
        elif name == 'native_ccd':
            m.opt.disableflags &= ~int(mujoco.mjtDisableBit.mjDSBL_NATIVECCD)
        results[name] = evaluate(m, row)
    original = results['original_mpr']
    assert original['contact_count'] == row['contact_count']
    assert abs(original['max_penetration_m']-row['penetration_m']) < 1e-14
    results['original_mpr_retreat_0p1um'] = evaluate(model, row, -1e-7)
    target.mkdir(parents=True)
    script = ROOT/'tools/validation/check_stop_contact_geometry.py'
    protocol = OUT/'冻结姿态核查协议.md'
    (target/script.name).write_bytes(script.read_bytes())
    (target/protocol.name).write_bytes(protocol.read_bytes())
    output = dict(diagnostic_only=True, mujoco_version=mujoco.__version__, sample_index=20,
                  time_s=row['time_s'], pose=row['position_m']+row['quaternion_wxyz'],
                  source_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in (script, protocol, prior/'baseline_0p2ms.json.gz')},
                  results=results)
    (target/'results.json').write_text(json.dumps(output, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    for name, value in results.items():
        print(name, value['contact_count'], value['max_penetration_m']*1e6,
              'pin07_main_contacts', len(value['pair_contacts']))


if __name__ == '__main__':
    main()
