"""Standalone static reproducer. Requires only mujoco and numpy; never calls mj_step."""
import argparse
import hashlib
import json
from pathlib import Path
import sys


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--models',type=Path,default=Path(__file__).parent/'minimal_v2')
    p.add_argument('--output',type=Path)
    p.add_argument('--package-path',type=Path,help='Optional isolated package directory; this process only')
    p.add_argument('--view',choices=['new_native','old_native','old_mpr'],help='Static passive viewer; no dynamics')
    args=p.parse_args()
    if args.output and args.output.exists():raise FileExistsError('Choose a new output path')
    if args.package_path:sys.path.insert(0,str(args.package_path.resolve()))
    import mujoco
    import numpy as np
    results=[];selected=None
    for name in ('new_native','old_native','old_mpr'):
        path=args.models/(name+'.xml');raw=path.read_bytes()
        m=mujoco.MjModel.from_xml_string(raw.decode('utf-8'));d=mujoco.MjData(m)
        mujoco.mj_resetDataKeyframe(m,d,0);mujoco.mj_forward(m,d)
        geometry=[]
        for g in range(m.ngeom):
            r=dict(name=m.geom(g).name,size=m.geom_size[g].tolist(),position=d.geom_xpos[g].tolist(),rotation=d.geom_xmat[g].tolist())
            if m.geom_type[g]==mujoco.mjtGeom.mjGEOM_MESH:
                mesh=m.geom_dataid[g];a=m.mesh_vertadr[mesh];r['vertices']=m.mesh_vert[a:a+m.mesh_vertnum[mesh]].tolist()
            geometry.append(r)
        contacts=[dict(depth_m=float(-c.dist),normal=c.frame[:3].tolist(),position=c.pos.tolist()) for c in d.contact]
        row=dict(name=name,xml_sha256=hashlib.sha256(raw).hexdigest(),ngeom=m.ngeom,nmesh=m.nmesh,
                 tolerance=m.opt.ccd_tolerance,disableflags=int(m.opt.disableflags),qpos=d.qpos.tolist(),
                 contact_count=int(d.ncon),contacts=contacts,geometry=geometry,
                 max_depth_m=max([0.]+[c['depth_m'] for c in contacts]))
        results.append(row);print(name,'max_depth_um',row['max_depth_m']*1e6,'contacts',d.ncon,flush=True)
        if args.view==name:selected=(m,d)
    record=dict(mujoco_version=mujoco.__version__,module_file=mujoco.__file__,static_only=True,results=results)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if selected:
        import time
        import mujoco.viewer
        m,d=selected
        with mujoco.viewer.launch_passive(m,d) as viewer:
            viewer.cam.lookat[:]=np.mean(d.geom_xpos,axis=0);viewer.cam.distance=.009
            viewer.cam.azimuth=140;viewer.cam.elevation=-20
            viewer.opt.flags[mujoco.mjtVisFlag.mjVIS_CONTACTPOINT]=True
            while viewer.is_running():viewer.sync();time.sleep(.03)


if __name__=='__main__':main()
