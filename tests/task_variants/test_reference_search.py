import copy,math
from dataclasses import replace
from types import SimpleNamespace
import numpy as np
import pytest


def obs(t=0.,p=(0.,0.,0.),ref=(0.,0.,0.),previous=(0.,0.),w=(0.,)*6):
    from tools.control.reference_search import DriveObservation
    return DriveObservation(t,p,w,0.,ref,previous)


def controller():
    from tools.control.reference_search import ReferenceSearchRecovery
    c=ReferenceSearchRecovery();c._start_search(obs());return c


def test_blocked_actual_position_does_not_change_reference_tracking_command():
    a=controller();b=copy.deepcopy(a);a.theta=b.theta=8.
    sa=obs(.2,p=(0.,0.,0.),ref=(20e-6,-40e-6,0.))
    sb=replace(sa,displacement_m=(-70e-6,60e-6,0.))
    assert np.array_equal(a.command(sa,.002),b.command(sb,.002))
    assert a.search_composition['tracking_xy_m_s']==b.search_composition['tracking_xy_m_s']


def test_stuck_pose_reference_follows_whole_bounded_search_without_windup():
    from tools.dynamics.safety import limit_command
    c=controller();ref=np.zeros(3);previous=np.zeros(6);maxradius=0.;maxerror=0.;count=0
    for i in range(4100):
        u=c.command(obs(i*.002,ref=tuple(ref),previous=tuple(previous[:2])),.002)
        if c.phase!='SEARCH':break
        previous=limit_command(u,previous,.002,np.array([.001]*3+[.03]*3),np.array([.005]*3+[.3]*3))
        ref[:2]+=previous[:2]*.002
        assert np.allclose(c.search_composition['predicted_reference_xy_m'],ref[:2],rtol=0,atol=1e-15)
        maxradius=max(maxradius,np.linalg.norm(ref[:2]));maxerror=max(maxerror,np.linalg.norm(ref[:2]-c.search_composition['target_xy_m']));count+=1
    assert c.phase=='WAIT_RECOVERY' and c.events[-1]['reason']=='SEARCH_EXHAUSTED'
    assert count>3500 and maxradius<=120e-6 and maxerror<10e-6


@pytest.mark.parametrize('ref,prev,phase,reason',[
    ((121e-6,0.,0.),(0.,0.),'FAILED','SEARCH_REFERENCE_LIMIT'),
    ((119.99e-6,0.,0.),(.0003,0.),'WAIT_RECOVERY','SEARCH_EXHAUSTED')])
def test_reference_gate_distinguishes_current_violation_from_next_search_exhaustion(ref,prev,phase,reason):
    c=controller();before=c.admittance.offset.copy()
    u=c.command(obs(.2,ref=ref,previous=prev),.002)
    assert c.phase==phase and c.events[-1]['reason']==reason and np.array_equal(u,np.zeros(6))
    assert np.array_equal(c.admittance.offset,before)
    assert c.search_composition is None


def test_xy_freezes_but_angles_integrate_once_and_z_is_unchanged():
    c=controller();c.admittance.offset[:2]=[10e-6,20e-6];c.admittance.velocity[:2]=[.0002,.0003]
    expected=copy.deepcopy(c.admittance);w=(.006,-.006,-.006,.0001,-.0002,0.)
    angular=expected.command(w,.002);before=(c.admittance.offset.copy(),c.admittance.velocity.copy())
    u=c.command(obs(.1,w=w),.002)
    assert np.array_equal(c.admittance.offset[:2],before[0][:2]) and np.array_equal(c.admittance.velocity[:2],before[1][:2])
    assert np.array_equal(c.admittance.offset[2:],expected.offset[2:]) and np.array_equal(u[3:],angular[3:])
    assert u[2]==pytest.approx(.0001)


@pytest.mark.parametrize('bad',['ref_nan','ref_shape','previous_nan','previous_speed','missing'])
@pytest.mark.parametrize('entry',['command','recovery'])
def test_invalid_drive_observation_never_mutates_state(bad,entry):
    c=controller();sample=obs(.2)
    if bad=='ref_nan':sample=replace(sample,reference_displacement_m=(0.,float('nan'),0.))
    if bad=='ref_shape':sample=replace(sample,reference_displacement_m=(0.,0.))
    if bad=='previous_nan':sample=replace(sample,previous_command_xy_m_s=(float('nan'),0.))
    if bad=='previous_speed':sample=replace(sample,previous_command_xy_m_s=(.0011,0.))
    if bad=='missing':sample=object()
    if entry=='recovery':c.phase='WAIT_RECOVERY'
    before=copy.deepcopy(c.__dict__)
    with pytest.raises(ValueError):
        if entry=='recovery':c.start_recovered_search(sample)
        else:c.command(sample,.002)
    assert c.phase==before['phase'] and c.events==before['events'] and c.search_count==before['search_count']
    assert c.episode_peak_z_m==before['episode_peak_z_m']


def test_nonsearch_commands_preserved():
    from tools.control.axis_search import AxisSearchRecovery
    from tools.control.reference_search import ReferenceSearchRecovery
    a=AxisSearchRecovery();b=ReferenceSearchRecovery()
    for phase,w in [('INSERT',(.002,.004,-.001,.0001,0.,0.)),('UNLOAD',(.002,.004,-.02,.0001,0.,0.))]:
        a.phase=b.phase=phase;s=obs(.1,w=w)
        assert np.array_equal(a.command(s,.002),b.command(s,.002))


def test_new_observation_uses_relative_drive_state_and_does_not_write_environment():
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()
    from tools.learning.reference_session import ReferenceSearchSession
    s=object.__new__(ReferenceSearchSession);s.initial=np.array([.001,.002,-.004]);s.env=SimpleNamespace(initial=np.array([.001,.002,-.004,1.,0.,0.,0.]))
    row=dict(time_s=.1,position_m=[.0011,.0022,-.003],quaternion_wxyz=[1.,0.,0.,0.],contact_wrench_M=[0.]*6,
        reference_qpos=[.00105,.00204,-.0035,1.,0.,0.,0.],limited_command_world=[.0001,-.0002,0.,0.,0.,0.])
    s.env.reference=np.array(row['reference_qpos']);s.env.command=np.array(row['limited_command_world'])
    before=copy.deepcopy(row);o=s.policy_observation(row)
    assert np.allclose(o.reference_displacement_m,[50e-6,40e-6,.0005],rtol=0,atol=1e-15)
    assert o.previous_command_xy_m_s==(.0001,-.0002) and row==before


def test_net_progress_and_load_priority_still_apply():
    c=controller();c.episode_peak_z_m=250e-6;c.phase='WAIT_RECOVERY'
    c.start_recovered_search(obs(.1,p=(0.,0.,-5e-6)));c.load_since=.1
    c.command(obs(.12,p=(0.,0.,96e-6),w=(.022,0.,-.008,0.,0.,0.)),.002)
    assert c.phase=='FAILED' and c.reason=='SEARCH_BUDGET_EXHAUSTED'


def test_observation_uses_live_reference_and_command_despite_cached_row():
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()
    from tools.learning.reference_session import ReferenceSearchSession
    s=object.__new__(ReferenceSearchSession);s.initial=np.zeros(3)
    s.env=SimpleNamespace(initial=np.array([0.,0.,0.,1.,0.,0.,0.]),reference=np.array([0.,0.,0.,1.,0.,0.,0.]),command=np.zeros(6))
    row=dict(time_s=.1,position_m=[0.,0.,0.],quaternion_wxyz=[1.,0.,0.,0.],contact_wrench_M=[0.]*6,
        reference_qpos=[50e-6,0.,0.,1.,0.,0.,0.],limited_command_world=[.0002,0.,0.,0.,0.,0.])
    o=s.policy_observation(row)
    assert o.reference_displacement_m==(0.,0.,0.) and o.previous_command_xy_m_s==(0.,0.)


def test_recovery_first_command_observes_reset_reference_without_physics():
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()
    from tools.learning.reference_session import ReferenceSearchSession
    from tools.learning.guarded_environment import LearningEnvironment
    from tools.dynamics.cartesian import DynamicConfig
    e=object.__new__(LearningEnvironment);e.config=DynamicConfig();e.phase='STOPPING';e._observation_ready=True
    e.initial=np.array([0.,0.,0.,1.,0.,0.,0.]);p=np.array([0.,0.,-.00025,1.,0.,0.,0.])
    e.data=SimpleNamespace(time=1.,qpos=p.copy(),qvel=np.zeros(6),qacc=np.zeros(6),qfrc_constraint=np.zeros(6),
        xpos=np.array([p[:3]]),xmat=np.eye(3).reshape(1,9),contact=SimpleNamespace(dist=np.array([])),warning=[])
    e.reference=p.copy();e.reference[0]=50e-6;e.command=np.array([.0002,0.,0.,0.,0.,0.]);e.raw_command=e.command.copy()
    e.recovery_start=e.initial.copy();e.recovery_count=1
    e.events=[dict(time_s=.5+i*.1,phase='STOPPING',reason=r) for i,r in enumerate(['B2_SEARCH_EXHAUSTED','RECOVERY_ACCEPTED','RECOVERY_DISTANCE_REACHED'])]
    e.peaks=dict(force_N=0.,torque_G_Nm=0.,penetration_m=0.)
    e.last_finite=dict(time_s=1.,position_m=p[:3].tolist(),quaternion_wxyz=p[3:].tolist(),velocity_world=[0.]*6,
        contact_wrench_M=[0.]*6,contact_wrench_G=[0.]*6,penetration_m=0.,reference_qpos=e.reference.tolist(),limited_command_world=e.command.tolist())
    s=object.__new__(ReferenceSearchSession);s.env=e;s.initial=np.zeros(3);s.controller=controller();s.controller.phase='WAIT_RECOVERY'
    s.controller.episode_peak_z_m=0.;s._ready=True;s._cache=None;s.done=s.task_finished=False
    s.reason=s.stop_time=None;s.wait_start=1.;s.recovery_state='WAIT_RESUME';s.guard_latched=False;s.cycle_id=0
    before=p.copy();snap=s.prepare_cycle();composition=s.controller.search_composition
    assert e.phase=='RUNNING' and s.controller.search_count==2 and s.recovery_state is None
    assert composition['reference_xy_m']==[0.,0.] and snap.base_command[0]>0
    assert composition['predicted_limited_xy_m_s'][0]==pytest.approx(1e-5)
    assert composition['predicted_reference_xy_m'][0]==pytest.approx(2e-8)
    assert np.array_equal(e.data.qpos,before) and e.data.time==1. and np.array_equal(e.command,np.zeros(6))
