"""Reduce frozen failures to two collision geoms without changing compiled geometry."""
import argparse
import copy
import json
import xml.etree.ElementTree as ET
import mujoco
import numpy as np
from tools.model.contact_development import build_xml
from tools.dynamics.cartesian import CartesianEnvironment,DynamicConfig
from tools.validation.validate_training_readiness import ROOT,sha,verify_hashes,new_target

OUT=ROOT/'deliverables/contact_minimal_reproducer'


def minimal_xml(segments,pin,hole,pose,*,native,tolerance):
    tree=ET.fromstring(build_xml(segments))
    for inc in tree.findall('include'):tree.remove(inc)
    for body in tree.findall('./worldbody/body'):
        for geom in list(body.findall('geom')):
            if geom.get('name') not in (pin,hole):body.remove(geom)
    mesh=tree.find(f'.//geom[@name="{hole}"]').get('mesh')
    for assets in tree.findall('asset'):
        for asset in list(assets):
            if asset.tag!='mesh' or asset.get('name')!=mesh:assets.remove(asset)
    tree.find('compiler').attrib.pop('meshdir',None)
    option=tree.find('option');option.set('ccd_tolerance',format(tolerance,'.17g'))
    flag=option.find('flag')
    if flag is None:flag=ET.SubElement(option,'flag')
    flag.set('nativeccd','enable' if native else 'disable')
    keyframe=ET.SubElement(tree,'keyframe')
    ET.SubElement(keyframe,'key',name='failure',qpos=' '.join(format(v,'.17g') for v in pose))
    ET.indent(tree,space='  ')
    return ET.tostring(tree,encoding='unicode')+'\n'


def pair_data(m,d,pin,hole):
    ids={m.geom(pin).id,m.geom(hole).id}
    rows=[dict(depth_m=float(-c.dist),normal=c.frame[:3].tolist(),position=c.pos.tolist())
          for c in d.contact if {int(c.geom1),int(c.geom2)}==ids]
    return dict(total_contacts=int(d.ncon),pair_contacts=rows,max_pair_depth_m=max([0.]+[r['depth_m'] for r in rows]))


def geometry(m,d,name):
    g=m.geom(name).id
    result={'size':m.geom_size[g].copy(),'position':d.geom_xpos[g].copy(),'rotation':d.geom_xmat[g].copy()}
    if m.geom_type[g]==mujoco.mjtGeom.mjGEOM_MESH:
        mesh=m.geom_dataid[g];a=m.mesh_vertadr[mesh];result['mesh']=m.mesh_vert[a:a+m.mesh_vertnum[mesh]].copy()
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--tag',required=True);target=new_target(OUT,p.parse_args().tag)
    newpath=ROOT/'deliverables/contact_consistency_repair/新增失败冻结姿态.json'
    oldpath=ROOT/'deliverables/dynamic_actuator_v1/ccd_diagnostic.json'
    mprpath=ROOT/'deliverables/stop_reliability/frozen_pose_v1/results.json'
    new=json.loads(newpath.read_text(encoding='utf-8'));old=json.loads(oldpath.read_text(encoding='utf-8'))
    mpr=json.loads(mprpath.read_text(encoding='utf-8'));verify_hashes(ROOT,old['historical_source_sha256'])
    paths=[newpath,oldpath,mprpath,ROOT/'tools/validation/minimize_contact_failure.py',
           ROOT/'tools/dynamics/cartesian.py',ROOT/'tools/model/contact_development.py',OUT/'执行协议.md']
    protected={p.relative_to(ROOT).as_posix():sha(p) for p in paths}
    target.mkdir(parents=True);results=[]
    fixtures=[('new_native',256,'pin_06','hole_convex256_06_main_218',new['pose'],True,1e-12),
              ('old_native',128,'pin_05','hole_convex128_05_main_013',old['frozen_qpos'],True,1e-9),
              ('old_mpr',256,'pin_07','hole_convex256_07_main_179',mpr['pose'],False,1e-9)]
    for name,n,pin,hole,pose,native,tol in fixtures:
        env=CartesianEnvironment(DynamicConfig(collision_backend='native' if native else 'mpr'),segments=n)
        m=env.model;m.opt.ccd_tolerance=tol;d=env.data;d.qpos[:]=pose;mujoco.mj_forward(m,d)
        full=pair_data(m,d,pin,hole)
        masked=copy.deepcopy(m);ids=[m.geom(pin).id,m.geom(hole).id]
        masked.geom_contype[:]=0;masked.geom_conaffinity[:]=0
        for g in ids:masked.geom_contype[g]=m.geom_contype[g];masked.geom_conaffinity[g]=m.geom_conaffinity[g]
        md=mujoco.MjData(masked);md.qpos[:]=pose;mujoco.mj_forward(masked,md)
        xml=minimal_xml(n,pin,hole,pose,native=native,tolerance=tol)
        (target/(name+'.xml')).write_text(xml,encoding='utf-8',newline='\n')
        mm=mujoco.MjModel.from_xml_string(xml);dd=mujoco.MjData(mm);mujoco.mj_resetDataKeyframe(mm,dd,0);mujoco.mj_forward(mm,dd)
        comparisons={}
        for g in (pin,hole):
            a=geometry(m,d,g);b=geometry(mm,dd,g)
            comparisons[g]={k:bool(np.array_equal(a[k],b[k])) for k in a}
        minimal=pair_data(mm,dd,pin,hole)
        record=dict(name=name,pose=pose,native=native,tolerance=tol,full=full,masked=pair_data(masked,md,pin,hole),
                    minimal=minimal,compiled_geometry_equal=comparisons,ngeom=mm.ngeom,nmesh=mm.nmesh,
                    reproduced=bool(full['pair_contacts']==minimal['pair_contacts'] and all(all(v.values()) for v in comparisons.values())))
        results.append(record);print(name,record['reproduced'],'depth um',minimal['max_pair_depth_m']*1e6,'geometry',comparisons,flush=True)
        buffer=np.empty(mujoco.mj_sizeModel(mm),dtype=np.uint8)
        mujoco.mj_saveModel(mm,buffer=buffer)
        (target/(name+'.mjb')).write_bytes(buffer.tobytes())
    verify_hashes(ROOT,protected);verify_hashes(ROOT,old['historical_source_sha256'])
    (target/'minimize_contact_failure.py').write_bytes((ROOT/'tools/validation/minimize_contact_failure.py').read_bytes())
    result=dict(mujoco_version=mujoco.__version__,input_sha256=protected,results=results,
                files={p.name:sha(p) for p in target.iterdir()})
    (target/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
