import importlib
import json
import mujoco
import numpy as np
import pytest
from tools.dynamics.cartesian import CartesianEnvironment
from tools.validation.validate_training_readiness import ROOT


def candidate(segments=256):
    spec=importlib.util.find_spec('tools.dynamics.contact_candidate')
    assert spec is not None, 'Versioned native tight-tolerance candidate not implemented'
    return importlib.import_module(spec.name).candidate_environment(segments=segments)


@pytest.mark.parametrize('segments',[128,256])
def test_candidate_fixes_old_native_depth_without_changing_compiled_geometry(segments):
    env=candidate(segments);old=CartesianEnvironment(segments=segments)
    for name in ('geom_size','geom_pos','geom_quat','mesh_vert','body_mass','body_inertia','geom_solref','geom_solimp','geom_friction'):
        assert np.array_equal(getattr(env.model,name),getattr(old.model,name)),name
    pose=json.loads((ROOT/'deliverables/dynamic_actuator_v1/ccd_diagnostic.json').read_text(encoding='utf-8'))['frozen_qpos']
    env.data.qpos[:]=pose;mujoco.mj_forward(env.model,env.data)
    assert 0 < -min(env.data.contact.dist) < 1e-8
    assert env.config.collision_backend=='native'
    assert env.model.opt.ccd_tolerance==1e-12
    assert env.metadata()['contact_candidate']=='native_tight_v1'


def test_candidate_detects_grazing_contact_and_separation():
    env=candidate()
    pose=json.loads((ROOT/'deliverables/stop_reliability/frozen_pose_v1/results.json').read_text(encoding='utf-8'))['pose']
    env.data.qpos[:]=pose;mujoco.mj_forward(env.model,env.data)
    assert env.data.ncon>0
    assert 3.4e-8 < -min(env.data.contact.dist) < 3.7e-8
    env.data.qpos[2]-=1e-7;mujoco.mj_forward(env.model,env.data)
    assert env.data.ncon==0
