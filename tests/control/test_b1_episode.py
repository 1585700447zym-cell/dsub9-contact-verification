import importlib
from dataclasses import replace
import numpy as np
import pytest
from tools.validation.run_contact_cases import ContactCase
from tools.dynamics.cartesian import CartesianEnvironment
from tools.control.fixed_admittance import FixedAdmittance


def api():return importlib.import_module('tools.validation.run_b1_baseline')


def test_success_requires_pose_speed_and_hold_not_only_z():
    a=api()
    row={'position_m':[0,0,0],'quaternion_wxyz':[1,0,0,0],
         'velocity_world':[0]*6,'contact_wrench_G':[0]*6,'penetration_m':0}
    assert a.geometric_finish(row)
    for field,value in [('position_m',[.0002,0,0]),('velocity_world',[0,0,.001,0,0,0]),
                        ('quaternion_wxyz',[.999847695,0,.017452406,0]),('penetration_m',40e-6)]:
        assert not a.geometric_finish(dict(row,**{field:value}))


def test_short_episode_logs_real_feedback_and_preserves_protection():
    case=replace(ContactCase.combined(),start_origin_z_m=-.00395)
    e=CartesianEnvironment(segments=256)
    r=api().run_episode(e,case,FixedAdmittance(),max_time=.5)
    assert r['controller']['name']=='B1_fixed_admittance'
    assert len(r['trace'])>2 and r['physical_steps']>0
    assert r['contact_observed']
    assert max(np.linalg.norm(x['admittance_velocity']) for x in r['trace'])>0
    assert r['termination']!='GEOMETRIC_SUCCESS'
    assert max(r['peaks']['drive_force_components_N'])<=e.config.force_limit_N+1e-12


def test_zero_feedback_logs_zero_correction_even_with_contact():
    case=replace(ContactCase.combined(),start_origin_z_m=-.00395)
    r=api().run_episode(CartesianEnvironment(segments=256),case,FixedAdmittance(feedback_enabled=False),max_time=.4)
    assert r['contact_observed']
    assert all(np.linalg.norm(x['admittance_velocity'])==0 for x in r['trace'])


def test_success_waits_a_full_hold_interval_after_first_qualifying_sample():
    case=replace(ContactCase.aligned(),start_origin_z_m=-1e-6)
    r=api().run_episode(CartesianEnvironment(segments=256),case,FixedAdmittance(),max_time=.2)
    assert r['termination']=='GEOMETRIC_SUCCESS'
    assert r['final']['time_s']-r['stop_time_s']>=.1-1e-10


def test_resume_rejects_changed_historical_inputs(tmp_path):
    import json
    p=tmp_path/'result.json'
    p.write_text(json.dumps({'source_sha256':{'code':'a'},'historical_source_sha256':{'model':'old'}}))
    with pytest.raises(RuntimeError):api().read_checkpoint(p,{'code':'a'},{'model':'new'})
