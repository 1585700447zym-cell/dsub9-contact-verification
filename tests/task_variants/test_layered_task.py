import copy,gzip,json,math
from pathlib import Path
import numpy as np
import pytest

def api():
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()
    from tools.model import layered_task
    return layered_task

def row(x=0.,z=0.):
    return dict(position_m=[x,0.,z],quaternion_wxyz=[1.,0.,0.,0.],velocity_world=[0.]*6,
                contact_wrench_G=[0.]*6,penetration_m=0.)

def final_row():
    root=Path(__file__).resolve().parents[2]
    return json.loads(gzip.decompress((root/'deliverables/task_variants/deadline25_20261004/run/y_neg_150.json.gz').read_bytes()))['trace'][-1]

def test_aligned_and_real_interference():
    m=api()
    assert m.layered_pin_clearance_m(row())==pytest.approx(100e-6,abs=1e-14)
    assert not m.layered_pin_fit(row(110e-6))

@pytest.mark.parametrize('overlap_nm,accepted',[
    (.9,True),(1.1,True),(5.,True),(9.9,True),(10.1,False),(1000.,False)])
def test_only_nanometre_contact_overlap_is_accepted(overlap_nm,accepted):
    m=api();state=row(100e-6+overlap_nm*1e-9)
    assert m.layered_pin_clearance_m(state)==pytest.approx(-overlap_nm*1e-9,abs=1e-14)
    assert m.layered_pin_fit(state) is accepted

def test_archived_wide_entry_counterexample_is_resolved_without_changing_old_referee():
    m=api()
    from tools.model.clearance_task import pin_fit,pin_clearance_m,finish_criteria
    from tools.model.functional_task import functional_finish as old_finish
    r=final_row();before=copy.deepcopy(r)
    assert pin_clearance_m(r)<-1e-6 and not pin_fit(r) and not old_finish(r,finish_criteria())
    assert m.layered_pin_clearance_m(r)==pytest.approx(7.450513432876067e-9,abs=1e-12)
    assert m.functional_finish(r,finish_criteria())
    assert r==before

@pytest.mark.parametrize('z',[-.01,-.0041,.01])
def test_no_main_bore_intersection_is_not_vacuous_success(z):
    m=api();assert not m.layered_pin_fit(row(z=z))

@pytest.mark.parametrize('field,value',[
    ('position_m',[float('nan'),0.,0.]),('position_m',[0.,0.]),
    ('quaternion_wxyz',[0.]*4),('quaternion_wxyz',[1.,float('inf'),0.,0.]),
    ('quaternion_wxyz',[1.,0.,0.]),('quaternion_wxyz',[0.,1.,0.,0.])])
def test_invalid_and_out_of_scope_poses_fail_closed(field,value):
    m=api();r=row();r[field]=value
    assert m.layered_pin_clearance_m(r)==-math.inf and not m.layered_pin_fit(r)

def test_quaternion_scale_and_sign_do_not_change_geometry():
    m=api();r=final_row();expected=m.layered_pin_clearance_m(r)
    for factor in [-1.,1e300,1e-300]:
        r2=copy.deepcopy(r);r2['quaternion_wxyz']=(np.array(r['quaternion_wxyz'])*factor).tolist()
        assert m.layered_pin_clearance_m(r2)==pytest.approx(expected,abs=1e-14)

@pytest.mark.parametrize('field,value',[
    ('position_m',[0.,0.,21e-6]),('velocity_world',[11e-6,0,0,0,0,0]),
    ('velocity_world',[0,0,0,.0011,0,0]),('contact_wrench_G',[.025,0,0,0,0,0]),
    ('contact_wrench_G',[0,0,0,.0005,0,0]),('penetration_m',31e-6),
    ('velocity_world',[float('nan')]*6)])
def test_other_functional_conditions_remain_required(field,value):
    m=api();from tools.model.clearance_task import finish_criteria
    r=row(100e-6+5e-9)
    assert m.layered_pin_fit(r)
    r[field]=value
    assert not m.functional_finish(r,finish_criteria())

def test_pin_only_checker_does_not_replace_depth_or_stability():
    m=api();from tools.model.clearance_task import finish_criteria
    r=row(z=-.002)
    assert m.layered_pin_fit(r) and not m.functional_finish(r,finish_criteria())

def test_layer_clipping_and_zero_tilt_boundaries():
    m=api();R=np.eye(3)
    # The pin is in the broad entry only: broad layer valid, narrow layer absent.
    assert m._layer_margin(np.array([.00015,0,.0001]),R,.0005,.00005,0,.00025,[0,0],.000675)>0
    assert m._layer_margin(np.array([.00015,0,.0001]),R,.0005,.00005,.00025,.0045,[0,0],.0006) is None
    # Touching the narrow shoulder is checked, not dropped as an empty interval.
    assert m._layer_margin(np.array([.00015,0,.0002]),R,.0005,.00005,.00025,.0045,[0,0],.0006)<0

def test_archived_near_wall_case_rejects_a_small_outward_translation():
    m=api();r=final_row();p=np.array(r['position_m']);p[:2]+=p[:2]/np.linalg.norm(p[:2])*1e-6;r['position_m']=p.tolist()
    assert not m.layered_pin_fit(r)

def test_new_session_uses_layered_finish_but_same_policy_observation():
    m=api();from tools.learning.layered_session import LayeredReferenceSession
    from tools.learning.reference_session import ReferenceSearchSession
    from tools.model.clearance_task import finish_criteria
    session=object.__new__(LayeredReferenceSession);session.finish_criteria=finish_criteria()
    assert session.completion_ready(final_row())
    assert LayeredReferenceSession.policy_observation is ReferenceSearchSession.policy_observation


def test_nano_contact_still_requires_continuous_hold_and_respects_peak_guard():
    m=api()
    from types import SimpleNamespace
    from tools.model.clearance_task import finish_criteria
    from tools.dynamics.cartesian import DynamicConfig
    from tools.learning.layered_session import LayeredReferenceSession
    def session():
        s=object.__new__(LayeredReferenceSession)
        s.finish_criteria=finish_criteria();s.geometry_checker=m.layered_pin_fit
        s.env=SimpleNamespace(phase='STOPPING',events=[],config=DynamicConfig(),data=SimpleNamespace(time=0.),
            peaks=dict(force_N=0.,torque_G_Nm=0.,penetration_m=0.),
            guard_facts=dict(contact_reasons=[],motion_reasons=[]))
        s.controller=SimpleNamespace(config=SimpleNamespace(settle_time_s=1.))
        s.reason='TARGET_PLANE_REACHED';s.stop_time=0.;s.hold_start=None
        s.guard_latched=False;s.task_finished=False
        return s

    def tick(s,t,overlap_nm=5.):
        s.env.data.time=t
        s._post_task_cycle(dict(row(100e-6+overlap_nm*1e-9),time_s=t))

    s=session()
    for t,overlap in [(0.,5.),(.08,10.1),(.1,5.),(.18,5.)]:tick(s,t,overlap)
    assert not s.task_finished
    tick(s,.2)
    assert s.task_finished and s.reason=='GEOMETRIC_SUCCESS'

    s=session();s.env.peaks['penetration_m']=31e-6
    for t in (0.,.1,.2):tick(s,t)
    assert s.reason!='GEOMETRIC_SUCCESS' and s.guard_latched and s.hold_start is None
