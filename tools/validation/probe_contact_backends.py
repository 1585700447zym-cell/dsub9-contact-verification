"""Small frozen-pose backend probe, not a new simulation configuration."""
import copy
import json
import mujoco
from tools.dynamics.cartesian import CartesianEnvironment
from tools.validation.validate_training_readiness import ROOT, sha, verify_hashes


def main():
    out = ROOT/'deliverables/contact_consistency_repair/backend_probe_v1'
    if out.exists(): raise FileExistsError(out)
    old = ROOT/'deliverables/dynamic_actuator_v1/ccd_diagnostic.json'
    recent = ROOT/'deliverables/stop_reliability/frozen_pose_v1/results.json'
    a=json.loads(old.read_text(encoding='utf-8')); b=json.loads(recent.read_text(encoding='utf-8'))
    verify_hashes(ROOT,a['historical_source_sha256']); verify_hashes(ROOT,b['source_sha256'])
    results=[]
    for name,segments,pose in [('native_failure_128',128,a['frozen_qpos']),
                               ('native_failure_256',256,a['frozen_qpos']),
                               ('mpr_stop_256',256,b['pose'])]:
        original=CartesianEnvironment(segments=segments).model
        for mode in ('mpr','native','native_single','native_tight','native_iterations'):
            m=copy.deepcopy(original)
            if mode!='mpr':m.opt.disableflags &= ~int(mujoco.mjtDisableBit.mjDSBL_NATIVECCD)
            if mode=='native_single':m.opt.disableflags |= int(mujoco.mjtDisableBit.mjDSBL_MULTICCD)
            if mode=='native_tight':m.opt.ccd_tolerance=1e-12
            if mode=='native_iterations':m.opt.ccd_iterations=350
            d=mujoco.MjData(m);d.qpos[:]=pose;mujoco.mj_forward(m,d)
            contacts=[dict(pair=[m.geom(int(c.geom1)).name,m.geom(int(c.geom2)).name],
                           depth_m=float(-c.dist),normal=c.frame[:3].tolist(),pos=c.pos.tolist()) for c in d.contact]
            depth=max([0.]+[c['depth_m'] for c in contacts])
            results.append(dict(fixture=name,segments=segments,pose=pose,mode=mode,
                                disableflags=int(m.opt.disableflags),tolerance=m.opt.ccd_tolerance,
                                iterations=m.opt.ccd_iterations,depth_m=depth,contacts=contacts))
            print(name,mode,'contacts',d.ncon,'depth_um',depth*1e6,flush=True)
    out.mkdir(parents=True)
    inputs=[old,recent,ROOT/'tools/validation/probe_contact_backends.py',out.parent/'执行协议.md']
    record=dict(mujoco_version=mujoco.__version__,input_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in inputs},results=results)
    (out/'results.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (out/'probe_contact_backends.py').write_bytes(inputs[2].read_bytes())


if __name__=='__main__':main()
