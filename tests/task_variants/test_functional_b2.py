import math
from types import SimpleNamespace

import pytest


@pytest.fixture(scope='module', autouse=True)
def runtime():
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()


def row(x=0., z=0., pitch=0.):
    return dict(position_m=[x, 0., z], quaternion_wxyz=[math.cos(pitch/2),0.,math.sin(pitch/2),0.],
                velocity_world=[0.]*6, contact_wrench_G=[0.]*6, penetration_m=0., time_s=.11)


def test_functional_fit_is_separate_from_precision():
    from tools.model.functional_task import functional_finish
    from tools.model.clearance_task import finish_criteria
    from tools.validation.run_b1_baseline import geometric_finish
    assert functional_finish(row(100e-6), finish_criteria())
    assert not geometric_finish(row(100e-6), finish_criteria())


@pytest.mark.parametrize('state', [row(z=-21e-6),row(101e-6),row(80e-6,pitch=math.radians(.5)),
                                  dict(row(),velocity_world=[2e-5,0,0,0,0,0]),
                                  dict(row(),penetration_m=31e-6),row(float('nan'))])
def test_functional_failure_cannot_be_hidden_by_relaxed_precision(state):
    from tools.model.functional_task import functional_finish
    from tools.model.clearance_task import finish_criteria
    assert not functional_finish(state, finish_criteria())


def test_functional_session_holds_continuously_and_cannot_override_guard():
    from tools.learning.functional_session import FunctionalCandidateSession
    from tools.model.clearance_task import finish_criteria
    from tools.dynamics.cartesian import DynamicConfig
    s=object.__new__(FunctionalCandidateSession)
    s.finish_criteria=finish_criteria();s.geometry_checker=None
    s.env=SimpleNamespace(phase='STOPPING',events=[],config=DynamicConfig(),peaks=dict(force_N=0.,torque_G_Nm=0.,penetration_m=0.),
                          guard_facts=dict(contact_reasons=[],motion_reasons=[]))
    s.controller=SimpleNamespace(config=SimpleNamespace(settle_time_s=1.))
    s.reason='TARGET_PLANE_REACHED';s.stop_time=0.;s.hold_start=None;s.guard_latched=False;s.task_finished=False
    for t,x in [(0.,100e-6),(.08,101e-6),(.1,100e-6),(.18,100e-6)]:
        s._post_task_cycle(dict(row(x),time_s=t))
    assert not s.task_finished
    s.env.guard_facts['motion_reasons']=['ROTATION_LIMIT']
    s._post_task_cycle(dict(row(100e-6),time_s=.22))
    assert s.reason=='MOTION_VIOLATION'
    assert s.hold_start is None


def observation(t, angle=1.6, force=-.02):
    from tools.control.risk_search import PoseObservation
    return PoseObservation(t,(0.,0.,0.),(0.,0.,force,0.,0.,0.),math.radians(angle))


def test_risk_must_persist_and_then_unloads_before_search():
    from tools.control.risk_search import RiskSearchRecovery
    c=RiskSearchRecovery()
    c.command(observation(.1),.002);c.command(observation(.14),.002)
    assert c.phase=='INSERT'
    command=c.command(observation(.15),.002)
    assert c.phase=='UNLOAD' and command[2]<0
    assert c.events[-1]['reason']=='LOADED_ROTATION_RISK'
    assert c.events[-1]['relative_rotation_rad']==pytest.approx(math.radians(1.6))
    c.command(observation(.16,force=0),.002)
    assert c.phase=='SEARCH' and c.search_count==1


def test_cleared_condition_resets_risk_clock_and_search_budget_still_applies():
    from tools.control.risk_search import RiskSearchRecovery
    c=RiskSearchRecovery()
    c.command(observation(.1),.002);c.command(observation(.14,force=0),.002)
    c.command(observation(.16),.002);c.command(observation(.2),.002)
    assert c.phase=='INSERT'
    c.search_count=2;c.command(observation(.22),.002)
    assert c.phase=='FAILED' and c.reason=='SEARCH_BUDGET_EXHAUSTED'


def test_invalid_rotation_rejected_without_state_change():
    from tools.control.risk_search import RiskSearchRecovery
    c=RiskSearchRecovery()
    with pytest.raises(ValueError):c.command(observation(.1,angle=float('nan')),.002)
    assert c.phase=='INSERT' and not c.events


def test_new_observation_uses_relative_sensors_not_hole_center():
    from tools.learning.functional_session import FunctionalCandidateSession
    s=object.__new__(FunctionalCandidateSession)
    s.initial=[.2,.3,.4];s.env=SimpleNamespace(initial=[.2,.3,.4,1.,0.,0.,0.])
    a=dict(row(.201,z=.405),position_m=[.201,.302,.405],contact_wrench_M=[0.]*6)
    obs=s.policy_observation(a)
    assert obs.displacement_m==pytest.approx((.001,.002,.005))
    assert obs.relative_rotation_rad==0.
    assert set(vars(obs))=={'time_s','displacement_m','wrench_M','relative_rotation_rad'}
