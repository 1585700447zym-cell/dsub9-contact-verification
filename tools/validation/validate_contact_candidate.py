"""Frozen local geometry and historical positive-witness gate for native_tight_v1."""
import argparse
import json
import mujoco
import numpy as np
from tools.dynamics.contact_candidate import candidate_environment
from tools.validation.validate_training_readiness import ROOT,sha,verify_hashes,new_target
from tools.validation.run_b2_search import read_run
from tools.validation.repair_contact_coverage import check_pose,summarize
from tools.validation.run_contact_cases import ContactCase

OUT=ROOT/'deliverables/contact_consistency_repair'


def inspect(model,pose):
    data=mujoco.MjData(model);data.qpos[:]=pose;mujoco.mj_forward(model,data)
    contacts=[]
    for c in data.contact:
        names=[model.geom(int(g)).name for g in (c.geom1,c.geom2)]
        for a,b in ((int(c.geom1),int(c.geom2)),(int(c.geom2),int(c.geom1))):
            if not (model.geom(a).name.startswith('pin_') and '_main_' in model.geom(b).name):continue
            r=data.geom_xmat[a].reshape(3,3)
            top=data.geom_xpos[a,2]+model.geom_size[a,1]*abs(r[2,2])+model.geom_size[a,0]*np.linalg.norm(r[2,:2])
            mesh=model.geom_dataid[b];adr=model.mesh_vertadr[mesh]
            v=model.mesh_vert[adr:adr+model.mesh_vertnum[mesh]].astype(float)
            low=(v@data.geom_xmat[b].reshape(3,3).T+data.geom_xpos[b])[:,2].min()
            upper=max(0.,float(top-low))
            contacts.append({'pair':names,'depth_m':float(-c.dist),'axial_bound_m':upper,
                             'within_bound':bool(-c.dist<=upper+1e-9),'normal':c.frame[:3].tolist()})
    finite=bool(np.isfinite(data.qacc).all() and np.isfinite(data.qfrc_constraint).all() and
                all(np.isfinite(c.frame).all() and np.isfinite(c.dist) for c in data.contact))
    warnings=[int(w.number) for w in data.warning]
    return dict(pose=list(pose),ncon=int(data.ncon),depth_m=max(0.,-float(min(data.contact.dist))) if data.ncon else 0.,
                finite=finite,warnings=warnings,contacts=contacts,
                passed=finite and not any(warnings) and all(c['within_bound'] for c in contacts))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--tag',required=True);args=parser.parse_args()
    target=new_target(OUT,args.tag)
    oldpath=ROOT/'deliverables/dynamic_actuator_v1/ccd_diagnostic.json'
    newpath=ROOT/'deliverables/stop_reliability/frozen_pose_v1/results.json'
    witnesspath=ROOT/'deliverables/v1_applicability/diagnostic_results.json'
    tracepath=ROOT/'deliverables/stop_reliability/diagnosis_v1/baseline_0p2ms.json.gz'
    old=json.loads(oldpath.read_text(encoding='utf-8'));new=json.loads(newpath.read_text(encoding='utf-8'))
    witness=json.loads(witnesspath.read_text(encoding='utf-8'));verify_hashes(ROOT,old['historical_source_sha256'])
    verify_hashes(ROOT,new['source_sha256'])
    sources=[oldpath,newpath,witnesspath,tracepath,OUT/'候选复验协议.md',
             ROOT/'tools/dynamics/contact_candidate.py',ROOT/'tools/validation/validate_contact_candidate.py']
    protected={p.relative_to(ROOT).as_posix():sha(p) for p in sources}
    models={n:candidate_environment(segments=n).model for n in (128,256)};groups=[]
    for label,n,pose in [('native_old128',128,old['frozen_qpos']),('native_old256',256,old['frozen_qpos']),('mpr_stop256',256,new['pose'])]:
        rows=[]
        for shift in np.linspace(-1e-7,1e-7,21):
            q=list(pose);q[2]+=float(shift);rows.append(inspect(models[n],q))
        jump=float(np.max(np.abs(np.diff([r['depth_m'] for r in rows]))))
        groups.append(dict(name=label,rows=rows,max_depth_jump_m=jump,passed=all(r['passed'] for r in rows) and jump<=11e-9))
    trajectory=[inspect(models[256],r['position_m']+r['quaternion_wxyz']) for r in read_run(tracepath)['trace']]
    coverage=[check_pose(models[256],ContactCase(**r['case']),r['depth_m'],r['geometry_witness']) for r in witness['coverage_audit']]
    coverage_summary=summarize(coverage)
    special=[]
    for label,pose,expect in [('separated',[0,0,-.005,1,0,0,0],False),('aligned_deep',[0,0,0,1,0,0,0],False),
                              ('wall_x',[100e-6,0,-.003,1,0,0,0],True),
                              ('retreated',[new['pose'][0],new['pose'][1],new['pose'][2]-1e-7,*new['pose'][3:]],False)]:
        r=inspect(models[256],pose);r.update(name=label,expected_contact=expect)
        r['passed']=r['passed'] and bool(r['ncon'])==expect;special.append(r)
    verify_hashes(ROOT,protected);verify_hashes(ROOT,old['historical_source_sha256'])
    passed=all(g['passed'] for g in groups) and all(r['passed'] for r in trajectory+special) and coverage_summary['gate_pass']
    target.mkdir(parents=True)
    for p in sources[4:]: (target/p.name).write_bytes(p.read_bytes())
    result=dict(passed=passed,candidate='native_tight_v1',mujoco_version=mujoco.__version__,input_sha256=protected,
                historical_source_sha256=old['historical_source_sha256'],groups=groups,trajectory=trajectory,
                coverage_summary=coverage_summary,coverage=coverage,special=special)
    (target/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(dict(passed=passed,groups=[{k:v for k,v in g.items() if k!='rows'} for g in groups],
                         trajectory_failures=sum(not r['passed'] for r in trajectory),coverage=coverage_summary,
                         special=[(r['name'],r['passed']) for r in special]),ensure_ascii=False),flush=True)


if __name__=='__main__':main()
