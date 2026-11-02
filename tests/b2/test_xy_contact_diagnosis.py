"""Geometric diagnosis must preserve sample timing and count pins, not sectors."""
import numpy as np
import pytest


def test_exact_sample_selection_rejects_extrapolation():
    from tools.validation.diagnose_b2_xy_contacts import sample_at
    run={'trace':[{'time_s':1.0},{'time_s':1.002}]}
    assert sample_at(run,1.002)['time_s']==1.002
    with pytest.raises(ValueError):sample_at(run,1.004)
    with pytest.raises(ValueError):sample_at(run,1.001)


def test_multiple_sector_contacts_are_one_active_pin():
    from tools.validation.diagnose_b2_xy_contacts import contact_summary
    contacts=[{'geoms':['pin_09',f'hole_convex256_09_main_{i}'],'position_m':[0,0,.00025], 'penetration_m':1e-6} for i in (180,181)]
    out=contact_summary(contacts)
    assert out['active_pins']==['pin_09']
    assert out['contact_points']==2
    assert out['per_pin']['pin_09']['points']==2
    assert out['z_range_mm']==pytest.approx([.25,.25])
    assert out['layers']==['main']


def test_no_contacts_does_not_invent_depth_or_force():
    from tools.validation.diagnose_b2_xy_contacts import contact_summary
    out=contact_summary([])
    assert out['active_pins']==[] and out['contact_points']==0
    assert out['z_range_mm'] is None
    assert 'force' not in out


def test_tip_rim_height_includes_tilt_not_just_center():
    from tools.validation.diagnose_b2_xy_contacts import rim_z_range
    r=np.array([[1.,0,0],[0,0,-1.],[0,1.,0]])
    assert rim_z_range(.00025,r,.0005)==pytest.approx([-.00025,.00075])
    assert rim_z_range(.00025,np.eye(3),.0005)==pytest.approx([.00025,.00025])
