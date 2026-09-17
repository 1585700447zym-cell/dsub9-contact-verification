"""Export a viewable copy of the current B1 model without changing its sources."""
import hashlib
import xml.etree.ElementTree as ET
import mujoco
import numpy as np
from tools.reporting.report_b1 import read_verified
from tools.model.contact_development import build_xml, radial_error
from tools.dynamics.cartesian import CartesianEnvironment
from tools.validation.run_b1_baseline import dump
from tools.validation.run_contact_cases import ROOT, _project_root_cwd


def main():
    index,runs=read_verified()
    output=ROOT/'deliverables/model_exports_256'
    output.mkdir(exist_ok=True)
    target=output/'dsub9_convex256_b1_mpr.xml'
    env=CartesianEnvironment(segments=256)
    if env.metadata()!=runs[0]['environment']:
        raise RuntimeError('Current environment differs from recorded B1 environment')
    tree=ET.fromstring(build_xml(256,file_directory=output))
    option=tree.find('option')
    option.set('timestep',str(env.config.timestep))
    flag=option.find('flag')
    if flag is None:flag=ET.SubElement(option,'flag')
    flag.set('nativeccd','disable')
    ET.indent(tree,space='  ')
    target.write_text(ET.tostring(tree,encoding='unicode')+'\n',encoding='utf-8',newline='\n')
    # This Windows MuJoCo runtime needs an ASCII relative XML path in this Chinese workspace.
    # Loading the exported file verifies all relative mesh/include references.
    with _project_root_cwd():
        loaded=mujoco.MjModel.from_xml_path(target.relative_to(ROOT).as_posix())
    checked=['body_mass','body_inertia','body_pos','body_quat','body_ipos','body_iquat',
             'jnt_type','jnt_pos','jnt_axis','jnt_limited','qpos0','dof_damping',
             'geom_type','geom_size','geom_pos','geom_quat','geom_dataid',
             'geom_contype','geom_conaffinity','geom_friction','geom_solref','geom_solimp',
             'geom_margin','geom_gap','mesh_vert','mesh_face']
    for name in checked:
        if not np.array_equal(getattr(loaded,name),getattr(env.model,name)):
            raise RuntimeError('Exported array differs: '+name)
    options={}
    for name in dir(env.model.opt):
        if name.startswith('_'):continue
        value=getattr(env.model.opt,name)
        if isinstance(value,(int,float,np.ndarray)):
            if not np.array_equal(value,getattr(loaded.opt,name)):
                raise RuntimeError('Exported option differs: '+name)
            options[name]=value.tolist() if isinstance(value,np.ndarray) else value
    dump(output/'导出核对记录.json',{
        'source_baseline_commit':'1645282','mujoco_version':mujoco.__version__,
        'file':target.name,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
        'source_sha256':index['source_sha256'],'historical_source_sha256':index['historical_source_sha256'],
        'export_script_sha256':hashlib.sha256(__import__('pathlib').Path(__file__).read_bytes()).hexdigest(),
        'checked_model_arrays':checked,'checked_options':options,'matches_B1_model':True,
        'hole_contact_geom_count':sum((mujoco.mj_id2name(loaded,mujoco.mjtObj.mjOBJ_GEOM,i) or '').startswith('hole_convex256_') for i in range(loaded.ngeom)),
        'maximum_radial_expansion_um':{'main':radial_error(.000575,256)*1e6,'entry':radial_error(.000675,256)*1e6},
        'environment':env.metadata(),'controller':runs[1]['controller'],
        'scope':'Model export only. Python drive, controller, reset, evaluation and guards remain in source code; XML alone does not replay B1.'})
    print(target)
    print('Reloaded model matches all checked B1 model arrays and numeric solver options.')


if __name__=='__main__':main()
