import importlib
import json
import mujoco
from tools.validation.validate_training_readiness import ROOT


def test_two_geom_scene_reproduces_new_failure_without_project_assets():
    spec=importlib.util.find_spec('tools.validation.minimize_contact_failure')
    assert spec is not None,'Minimal contact reproducer is not implemented'
    api=importlib.import_module(spec.name)
    saved=json.loads((ROOT/'deliverables/contact_consistency_repair/新增失败冻结姿态.json').read_text(encoding='utf-8'))
    xml=api.minimal_xml(256,'pin_06','hole_convex256_06_main_218',saved['pose'],native=True,tolerance=1e-12)
    assert 'file=' not in xml and '<include' not in xml
    m=mujoco.MjModel.from_xml_string(xml);d=mujoco.MjData(m);mujoco.mj_resetDataKeyframe(m,d,0);mujoco.mj_forward(m,d)
    assert m.ngeom==2 and m.nmesh==1
    assert abs(-min(d.contact.dist)-saved['depth_m'])<1e-14
