"""Static-only perturbation and coordinate-expression diagnostics; never integrate."""
import argparse
import json
import xml.etree.ElementTree as ET
import mujoco
import numpy as np
from tools.validation.validate_training_readiness import ROOT,sha,verify_hashes,new_target

OUT=ROOT/'deliverables/contact_minimal_reproducer'


def transform_xml(xml,scale=1.,translation=None,shift=0.):
    tree=ET.fromstring(xml)
    def multiply(node,key):
        if key in node.attrib:node.set(key,' '.join(format(float(x)*scale,'.17g') for x in node.get(key).split()))
    for node in tree.iter():
        for key in ('pos','size','vertex'):multiply(node,key)
    opt=tree.find('option');opt.set('ccd_tolerance',format(float(opt.get('ccd_tolerance'))*scale,'.17g'))
    key=tree.find('./keyframe/key');q=np.array([float(x) for x in key.get('qpos').split()]);q[:3]*=scale
    q[2]+=shift*scale
    if translation is not None:
        translation=np.asarray(translation)*scale
        female=tree.find('.//body[@name="female"]')
        p=np.array([float(x) for x in female.get('pos','0 0 0').split()])+translation
        female.set('pos',' '.join(format(x,'.17g') for x in p));q[:3]+=translation
    key.set('qpos',' '.join(format(x,'.17g') for x in q));return ET.tostring(tree,encoding='unicode')


def evaluate(xml,scale,translation):
    m=mujoco.MjModel.from_xml_string(xml);d=mujoco.MjData(m);mujoco.mj_resetDataKeyframe(m,d,0);mujoco.mj_forward(m,d)
    pin=next(g for g in range(m.ngeom) if m.geom_type[g]==mujoco.mjtGeom.mjGEOM_CYLINDER)
    hole=1-pin;mesh=m.geom_dataid[hole];a=m.mesh_vertadr[mesh]
    v=m.mesh_vert[a:a+m.mesh_vertnum[mesh]].astype(float)
    verts=(v@d.geom_xmat[hole].reshape(3,3).T+d.geom_xpos[hole])/scale-translation
    pos=d.geom_xpos[pin]/scale-translation;r=d.geom_xmat[pin].reshape(3,3);size=m.geom_size[pin]/scale
    top=pos[2]+size[1]*abs(r[2,2])+size[0]*np.linalg.norm(r[2,:2]);bound=max(0.,float(top-verts[:,2].min()))
    return dict(ncon=int(d.ncon),depth_m=max([0.]+[-float(c.dist)/scale for c in d.contact]),
                axial_bound_m=bound,normals=[c.frame[:3].tolist() for c in d.contact],
                cylinder_position=pos.tolist(),cylinder_size=size.tolist(),cylinder_rotation=r.tolist(),
                world_mesh_vertices=verts.tolist(),warnings=[int(w.number) for w in d.warning])


def main():
    p=argparse.ArgumentParser();p.add_argument('--tag',required=True);args=p.parse_args();target=new_target(OUT,args.tag)
    source=OUT/'minimal_v2';index=json.loads((source/'results.json').read_text(encoding='utf-8'));verify_hashes(source,index['files'])
    protected={p.relative_to(ROOT).as_posix():sha(p) for p in [source/'results.json',OUT/'微扰与坐标表达协议.md',ROOT/'tools/validation/probe_minimal_coordinates.py']}
    rows=[]
    for name in ('new_native','old_native','old_mpr'):
        xml=(source/(name+'.xml')).read_text(encoding='utf-8');baseline=evaluate(xml,1.,np.zeros(3))
        for label,scale,t,shift in [('baseline',1.,[0.,0.,0.],0.),('retreat_1nm',1.,[0.,0.,0.],-1e-9),
                                   ('advance_1nm',1.,[0.,0.,0.],1e-9),('translate_1mm',1.,[.001,.001,.001],0.),
                                   ('length_unit_x1000',1000.,[0.,0.,0.],0.)]:
            r=evaluate(transform_xml(xml,scale,t,shift),scale,np.array(t))
            expected=np.array(baseline['cylinder_position'])+[0,0,shift]
            r.update(fixture=name,variant=label,scale=scale,translation=t,axial_shift_m=shift,
                     mesh_coordinate_error_m=float(np.max(np.abs(np.array(r['world_mesh_vertices'])-baseline['world_mesh_vertices']))),
                     cylinder_position_error_m=float(np.max(np.abs(np.array(r['cylinder_position'])-expected))),
                     collision_query_only=True)
            rows.append(r);print(name,label,'depth um',r['depth_m']*1e6,'bound um',r['axial_bound_m']*1e6,'mesh delta nm',r['mesh_coordinate_error_m']*1e9,flush=True)
    verify_hashes(ROOT,protected);target.mkdir(parents=True)
    (target/'results.json').write_text(json.dumps(dict(input_sha256=protected,results=rows),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (target/'probe_minimal_coordinates.py').write_bytes((ROOT/'tools/validation/probe_minimal_coordinates.py').read_bytes())


if __name__=='__main__':main()
