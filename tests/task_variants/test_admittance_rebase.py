from types import SimpleNamespace
import copy
import numpy as np
import pytest


@pytest.fixture(scope='module',autouse=True)
def runtime():
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()


def fixture():
    from tools.control.load_search import LoadSearchRecovery
    from tools.learning.rebase_session import RebasedLoadReliefSession
    c=LoadSearchRecovery();c.phase='UNLOAD';c.search_count=1;c.reference_release_requested=True
    c.admittance.offset[:]=[.0002,.0005,.03,-.02]
    c.admittance.velocity[:]=[.0001,0.,.002,-.003];c.admittance.limited_steps=91
    c.events=[dict(time_s=8.486,phase='UNLOAD',reason='SEARCH_LATERAL_LOAD')]
    s=object.__new__(RebasedLoadReliefSession);s.controller=c
    s.env=SimpleNamespace(phase='RUNNING',guard_facts=dict(simulation_valid=True,contact_reasons=[],motion_reasons=[]),
        reference=np.array([.0001,-.0003,-.0038,1.,0.,0.,0.]),
        data=SimpleNamespace(qpos=np.array([0.,-.00016,-.004,1.,0.,0.,0.]),qvel=np.array([.0001,0.,0.,0.,0.,0.]),time=8.486))
    return s,SimpleNamespace(base_command=[0.,0.,-.00025,.002,-.003,0.],time_s=8.486)


def test_reference_and_admittance_xy_rebase_once_preserving_physics_and_angular_state():
    s,snapshot=fixture();before=copy.deepcopy(s.env);a=s.controller.admittance
    assert s._command_for_action(snapshot,np.zeros(4))==snapshot.base_command
    assert np.array_equal(s.env.reference[:2],before.data.qpos[:2])
    assert np.array_equal(s.env.reference[2:],before.reference[2:])
    assert np.array_equal(s.env.data.qpos,before.data.qpos)
    assert np.array_equal(s.env.data.qvel,before.data.qvel) and s.env.data.time==before.data.time
    assert s.env.guard_facts==before.guard_facts
    assert a.offset.tolist()==[0.,0.,.03,-.02]
    assert a.velocity.tolist()==[0.,0.,.002,-.003] and a.limited_steps==91
    e=s.controller.events[-1]
    assert e['reason']=='XY_ADMITTANCE_REBASED'
    assert e['offset_before_m']==[.0002,.0005] and e['offset_after_m']==[0.,0.]
    assert e['per_segment_budget_m']==[.0005,.0005]
    count=len(s.controller.events);a.offset[1]=1e-6;s.env.reference[0]=2e-6
    s._command_for_action(snapshot,np.zeros(4))
    assert a.offset[1]==1e-6 and s.env.reference[0]==2e-6 and len(s.controller.events)==count


def test_rebased_saturated_state_can_respond_to_positive_force_with_same_limits():
    s,snapshot=fixture();a=s.controller.admittance
    old=copy.deepcopy(a);w=[0.,.0204315783,0.,0.,0.,0.]
    assert old.command(w,.002)[1]==0.
    s._command_for_action(snapshot,np.zeros(4))
    result=a.command(w,.002)
    assert 0.<result[1]<=.0005 and a.offset[1]<=.0005
    assert a.config==old.config


@pytest.mark.parametrize('bad', ['nan_offset','bad_velocity_shape','guard','exhausted_budget'])
def test_invalid_rebase_fails_before_either_reference_or_integrator_changes(bad):
    s,snapshot=fixture();a=s.controller.admittance
    if bad=='nan_offset':a.offset[1]=float('nan')
    if bad=='bad_velocity_shape':a.velocity=np.zeros(3)
    if bad=='guard':s.env.guard_facts['contact_reasons']=['FORCE_LIMIT']
    if bad=='exhausted_budget':s.controller.search_count=2
    reference=s.env.reference.copy();offset=a.offset.copy();velocity=a.velocity.copy();events=copy.deepcopy(s.controller.events)
    with pytest.raises((ValueError,RuntimeError)):s._command_for_action(snapshot,np.zeros(4))
    assert np.array_equal(reference,s.env.reference)
    assert np.array_equal(offset,a.offset,equal_nan=True) and np.array_equal(velocity,a.velocity,equal_nan=True)
    assert s.controller.reference_release_requested and s.controller.events==events


def test_no_release_request_retains_integral_even_if_saturated():
    s,snapshot=fixture();s.controller.reference_release_requested=False;a=s.controller.admittance
    reference=s.env.reference.copy();offset=a.offset.copy();velocity=a.velocity.copy()
    s._command_for_action(snapshot,np.zeros(4))
    assert np.array_equal(reference,s.env.reference)
    assert np.array_equal(offset,a.offset) and np.array_equal(velocity,a.velocity)
