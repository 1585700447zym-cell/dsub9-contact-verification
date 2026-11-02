"""Regression cases that previously had geometric overlap but no contact."""
import importlib
import math
from pathlib import Path

import mujoco
import numpy as np
import pytest

from tools.validation.run_contact_cases import ContactCase, _quaternion, _male_world_wrench


def module():
    return importlib.import_module('tools.model.contact_development')


@pytest.mark.parametrize('segments', [32, 64, 128, 256])
def test_convex_hole_error_is_bounded_and_does_not_shrink_nominal_hole(segments):
    m = module()
    vertices = m.sector_vertices(.000575, .001, .00025, .0045, segments, 0)
    midpoint = (vertices[0]+vertices[3])/2
    assert np.hypot(*midpoint[:2]) == pytest.approx(.000575, abs=1e-14)
    assert np.hypot(*vertices[0,:2])-.000575 == pytest.approx(m.radial_error(.000575, segments))
    if segments == 128:
        assert m.radial_error(.000675, segments) < .204e-6


def test_roll_full_depth_contact_is_found_on_all_nine_pins():
    m = module().load_model(128)
    d = mujoco.MjData(m)
    d.qpos[:7] = (0, 0, 0, *_quaternion(ContactCase.roll(math.radians(1.5))))
    mujoco.mj_forward(m, d)
    names = {mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, int(g))
             for c in d.contact for g in (c.geom1,c.geom2)}
    assert {f'pin_{i:02}' for i in range(1,10)} <= names


@pytest.mark.parametrize('case', [ContactCase.aligned(), ContactCase.separated()])
def test_aligned_and_separated_remain_contact_free(case):
    m=module().load_model(128);d=mujoco.MjData(m)
    z=0 if case.name=='aligned' else -.005
    d.qpos[:7]=(0,0,z,1,0,0,0)
    mujoco.mj_forward(m,d)
    assert d.ncon==0


@pytest.mark.parametrize('axis,offset', [(0, .0001), (0, -.0001), (1, .0001), (1, -.0001)])
def test_pin_force_opposes_lateral_offset(axis, offset):
    m=module().load_model(128);d=mujoco.MjData(m)
    d.qpos[:7]=(0,0,0,1,0,0,0);d.qpos[axis]=offset;mujoco.mj_forward(m,d)
    male=mujoco.mj_name2id(m,mujoco.mjtObj.mjOBJ_BODY,'male')
    wrench,_=_male_world_wrench(m,d,male)
    assert np.isfinite(wrench).all()
    assert wrench[axis]*offset<0


def test_invalid_resolution_and_tolerance_are_rejected():
    m=module()
    with pytest.raises(ValueError):m.load_model(7)
    with pytest.raises(ValueError):m.load_model(128.0)
    with pytest.raises(ValueError):m.load_model(128,ccd_tolerance=float('nan'))


def test_development_loader_does_not_modify_formal_model():
    from tools.validation.run_contact_cases import FORMAL_MODEL
    before=FORMAL_MODEL.read_bytes()
    module().load_model(64)
    assert FORMAL_MODEL.read_bytes()==before


def test_exported_xml_and_loader_have_identical_numerical_options():
    from tools.validation.run_contact_cases import _project_root_cwd
    with _project_root_cwd():
        exported=mujoco.MjModel.from_xml_string(module().build_xml())
    loaded=module().load_model()
    for key in ('timestep','ccd_tolerance','iterations','tolerance'):
        assert getattr(exported.opt,key)==getattr(loaded.opt,key)


def test_coverage_checker_catches_old_miss_and_accepts_replacement():
    from tools.validation import repair_contact_coverage as check
    from tools.validation.run_contact_cases import _load_model
    c=ContactCase.roll(math.radians(1.5))
    witness=check.fast_witness(c,.004)
    old=check.check_pose(_load_model('sdf',.0002),c,.004,witness)
    new=check.check_pose(module().load_model(),c,.004,witness)
    assert len(old['missing_pins'])==9
    assert new['missing_pins']==[]
    assert new['finite'] and new['status']=='OK'


def test_coverage_checker_keeps_sdf_capacity_error_as_failure():
    from tools.validation import repair_contact_coverage as check
    from tools.validation.run_contact_cases import _load_model
    m=_load_model('sdf',.0002)
    previous=m.opt.sdf_initpoints
    try:
        m.opt.sdf_initpoints=1000
        c=ContactCase.roll(math.radians(1.5))
        result=check.check_pose(m,c,.0005,check.fast_witness(c,.0005))
        assert result['status']=='SIMULATION_ERROR'
        assert 'too many contact points' in result['error']
    finally:m.opt.sdf_initpoints=previous
