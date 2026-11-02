from types import SimpleNamespace
import numpy as np
import pytest


@pytest.fixture(scope='module',autouse=True)
def runtime():
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()


def obs(t,fx=.022,fy=0.,fz=-.008):
    from tools.control.risk_search import PoseObservation
    return PoseObservation(t,(0.,0.,0.),(fx,fy,fz,0.,0.,0.),0.)


def controller():
    from tools.control.load_search import LoadSearchRecovery
    c=LoadSearchRecovery();c._start_search(obs(0.,fx=0.));return c


def test_persistent_lateral_load_pauses_search_and_requires_reference_release():
    c=controller();c.command(obs(.1),.002);c.command(obs(.118),.002)
    assert c.phase=='SEARCH'
    theta=c.theta;command=c.command(obs(.12),.002)
    assert c.phase=='UNLOAD' and c.theta==theta
    assert list(command[:2])==[0.,0.] and command[2]<0
    assert c.reference_release_requested
    assert c.events[-1]['reason']=='SEARCH_LATERAL_LOAD'
    with pytest.raises(RuntimeError,match='reference'):c.command(obs(.122),.002)


def test_load_clearing_resets_clock_and_axial_only_does_not_trigger():
    c=controller();c.command(obs(.1),.002);c.command(obs(.118,fx=0.,fz=-.024),.002)
    c.command(obs(.12),.002);c.command(obs(.138),.002)
    assert c.phase=='SEARCH' and not c.reference_release_requested


def test_existing_search_budget_cannot_be_extended_by_load_relief():
    c=controller();c.search_count=2;c.command(obs(.1),.002);c.command(obs(.12),.002)
    assert c.phase=='FAILED' and c.reason=='SEARCH_BUDGET_EXHAUSTED'
    assert not c.reference_release_requested


def test_invalid_observation_does_not_mutate_pending_state():
    c=controller();c.command(obs(.1),.002);since=c.load_since
    with pytest.raises(ValueError):c.command(obs(.12,fx=float('nan')),.002)
    assert c.phase=='SEARCH' and c.load_since==since


def session_fixture():
    from tools.learning.load_session import LoadReliefSession
    c=controller();c.command(obs(.1),.002);c.command(obs(.12),.002)
    s=object.__new__(LoadReliefSession);s.controller=c
    s.env=SimpleNamespace(phase='RUNNING',guard_facts=dict(simulation_valid=True,contact_reasons=[],motion_reasons=[]),
        reference=np.array([.00015,-.00017,-.0038,1.,0.,0.,0.]),
        data=SimpleNamespace(qpos=np.array([0.,0.,-.004,1.,0.,0.,0.]),qvel=np.array([.0001,0.,0.,0.,0.,0.]),time=.12))
    return s,SimpleNamespace(base_command=[0.,0.,-.00025,0.,0.,0.],time_s=.12)


def test_reference_release_is_once_and_never_teleports_physical_state():
    s,snapshot=session_fixture();q=s.env.data.qpos.copy();v=s.env.data.qvel.copy();other=s.env.reference[2:].copy()
    assert s._command_for_action(snapshot,np.zeros(4))==snapshot.base_command
    assert np.array_equal(s.env.data.qpos,q) and np.array_equal(s.env.data.qvel,v) and s.env.data.time==.12
    assert np.array_equal(s.env.reference[:2],q[:2]) and np.array_equal(s.env.reference[2:],other)
    assert not s.controller.reference_release_requested
    count=len(s.controller.events);s.env.reference[0]=1e-6
    s._command_for_action(snapshot,np.zeros(4))
    assert s.env.reference[0]==1e-6 and len(s.controller.events)==count
    s.controller.command(obs(.122,fx=0.,fz=0.),.002)
    assert s.controller.phase=='SEARCH' and s.controller.search_count==2


def test_guarded_environment_never_releases_reference():
    s,snapshot=session_fixture();s.env.guard_facts['motion_reasons']=['ROTATION_LIMIT'];old=s.env.reference.copy()
    with pytest.raises(RuntimeError):s._command_for_action(snapshot,np.zeros(4))
    assert np.array_equal(old,s.env.reference)


@pytest.mark.parametrize('boundary,phase,reason',[
    ('excursion','FAILED','SEARCH_EXCURSION_LIMIT'),
    ('advance','INSERT','SEARCH_ADVANCED'),
    ('timeout','WAIT_RECOVERY','SEARCH_EXHAUSTED'),
    ('radius','WAIT_RECOVERY','SEARCH_EXHAUSTED')])
def test_original_search_boundaries_take_priority_over_new_load_trigger(boundary,phase,reason):
    import math
    from dataclasses import replace
    c=controller();c.command(obs(.1),.002)
    sample=obs(.12)
    if boundary=='excursion':sample=replace(sample,displacement_m=(201e-6,0.,0.))
    if boundary=='advance':sample=replace(sample,displacement_m=(0.,0.,100e-6))
    if boundary=='timeout':c.config=replace(c.config,search_time_s=.12)
    if boundary=='radius':c.theta=6*math.pi
    c.command(sample,.002)
    assert c.phase==phase and c.events[-1]['reason']==reason
    assert not c.reference_release_requested
