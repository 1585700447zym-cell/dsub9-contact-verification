import copy,json,math
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest

@pytest.fixture(scope='module',autouse=True)
def runtime():
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()

def examples():
    p=Path(__file__).resolve().parents[2]/'deliverables/paper_comparison/protocol_v4_20261004/residual_integration_audit.json'
    return json.loads(p.read_text(encoding='utf8'))['examples']

def test_all_six_archived_counterexamples_are_filtered_without_breaking_slew():
    from tools.learning.v4_action import compose_reference_command
    from tools.dynamics.safety import limit_command
    for e in examples():
        cmd,log=compose_reference_command(e['base_command'],e['normalized_action'],phase='SEARCH',enabled=True,
             previous_limited=e['previous_limited_command'],dt=.002,reference_xy=e['reference_xy_m'])
        actual=limit_command(cmd,e['previous_limited_command'],.002,[.001]*3+[.03]*3,[.005]*3+[.3]*3)
        assert np.linalg.norm(np.array(e['reference_xy_m'])+actual[:2]*.002)<=.00012+1e-12
        assert 0<=log['reference_filter_fraction']<1
        assert np.linalg.norm(np.array(e['reference_xy_m'])+actual[:2]*.002)<.00012
        np.testing.assert_array_equal(actual,log['predicted_limited_command'])
        assert log['experience_action']==e['normalized_action']

def test_zero_and_interior_action_preserve_existing_command_and_log():
    from tools.learning.v4_action import compose_reference_command,SCALE
    from tools.learning.action import compose_command
    for phase,enabled,action in [('SEARCH',True,[0]*4),('SEARCH',True,[.1]*4),('INSERT',True,[1]*4),('UNLOAD',False,[1]*4)]:
        args=dict(phase=phase,enabled=enabled,previous_limited=[0]*6,dt=.002)
        old,oldlog=compose_command([0]*6,action,action_scale=SCALE,**args)
        new,log=compose_reference_command([0]*6,action,reference_xy=[0,0],**args)
        np.testing.assert_array_equal(old,new)
        for k,v in oldlog.items():assert log[k]==v
        assert log['reference_filter_fraction']==1

def test_infeasible_baseline_and_nonfinite_reference_rejected():
    from tools.learning.v4_action import compose_reference_command,ReferenceEnvelopeInfeasible
    args=dict(phase='SEARCH',enabled=True,previous_limited=[.0001,0,0,0,0,0],dt=.002)
    with pytest.raises(ReferenceEnvelopeInfeasible):compose_reference_command([0]*6,[0]*4,reference_xy=[.00012,0],**args)
    with pytest.raises(ValueError):compose_reference_command([0]*6,[0]*4,reference_xy=[float('nan'),0],**args)
    with pytest.raises(ValueError):compose_reference_command([0]*6,[0]*4,reference_xy=None,**args)
    with pytest.raises(ValueError):compose_reference_command([0]*6,[float('nan')]*4,phase='UNLOAD',enabled=False,previous_limited=[0]*6,dt=.002)

def test_random_boundary_interpolation_remains_in_disk_and_driver_box():
    from tools.learning.v4_action import compose_reference_command
    rng=np.random.default_rng(44)
    for _ in range(300):
        angle=rng.uniform(-math.pi,math.pi);ref=.00012*rng.uniform(.999,1)*np.array([math.cos(angle),math.sin(angle)])
        command,log=compose_reference_command([0]*6,rng.uniform(-1,1,4),phase='SEARCH',enabled=True,
            previous_limited=[0]*6,dt=.002,reference_xy=ref)
        limited=np.array(log['predicted_limited_command'])
        assert np.linalg.norm(ref+limited[:2]*.002)<=.00012+1e-12
        assert np.max(np.abs(limited[:3]))<=.005*.002+1e-15

def fake_session(mode='F50'):
    from tools.learning.v4_session import V4ResidualSession
    from tools.learning.guarded_environment import LearningEnvironment
    from tools.control.reference_search import ReferenceSearchRecovery
    from tools.control.search_recovery import SearchConfig
    env=object.__new__(LearningEnvironment)
    env.config=SimpleNamespace(control_period=.002,linear_speed=.001,linear_acceleration=.005,angular_speed=.03,angular_acceleration=.3)
    s=V4ResidualSession(environment=env,mode=mode,controller_factory=lambda:ReferenceSearchRecovery(SearchConfig(total_action_time_s=25.)))
    s.controller=s.controller_factory();s.initial=np.array([0,0,-.004])
    env.phase='RUNNING';env.reference=np.array([.0001,-.0003,-.0038,1,0,0,0.]);env.command=np.zeros(6)
    env.data=SimpleNamespace(qpos=np.array([0.,-.00016,-.004,1,0,0,0]),qvel=np.zeros(6),time=1.)
    env._facts=dict(simulation_valid=True,contact_reasons=[],motion_reasons=[],invalid_reasons=[])
    return s

def test_session_preserves_release_rebase_and_masks_actions():
    s=fake_session();c=s.controller;c.phase='UNLOAD';c.search_count=1;c.reference_release_requested=True
    c.admittance.offset[:]=[.0002,.0005,.03,-.02];c.admittance.velocity[:]=[.0001,0,.002,-.003]
    before=copy.deepcopy(s.env.data)
    snap=SimpleNamespace(base_command=[0,0,-.00025,.002,-.003,0],time_s=1.,controller_state={'phase':'UNLOAD'},residual_enabled=False)
    s._command_for_action(snap,[1]*4)
    np.testing.assert_array_equal(s.env.reference[:2],s.env.data.qpos[:2])
    assert c.admittance.offset.tolist()==[0,0,.03,-.02]
    assert c.admittance.velocity.tolist()==[0,0,.002,-.003]
    np.testing.assert_array_equal(s.env.data.qpos,before.qpos)
    assert s.last_action_log['experience_action']==[0]*4
    assert [e['reason'] for e in c.events]==['XY_REFERENCE_RELEASED','XY_ADMITTANCE_REBASED']

@pytest.mark.parametrize('mode,phase,expected',[('F50','INSERT',True),('F50','SEARCH',True),('S50','INSERT',False),('S50','SEARCH',True),('S50','UNLOAD',False)])
def test_stage_permission(mode,phase,expected):
    s=fake_session(mode)
    assert s.stage_permission(phase,True)==expected
    assert s.stage_permission(phase,False) is False

def test_new_session_retains_layered_and_reference_observation_mro():
    from tools.learning.layered_session import LayeredReferenceSession
    from tools.learning.residual_session import ResidualSession
    s=fake_session()
    assert isinstance(s,(LayeredReferenceSession,ResidualSession))
    assert s.completion_ready.__func__ is LayeredReferenceSession.completion_ready
    with pytest.raises(ValueError):fake_session('OLD')

def test_b1_is_exact_fixed_admittance_and_never_searches():
    from tools.control.v4_b1 import V4FixedAdmittance
    from tools.control.fixed_admittance import FixedAdmittance
    from tools.control.search_recovery import Observation
    c=V4FixedAdmittance();reference=FixedAdmittance()
    for i in range(400):
        w=[.01,-.01,-.024,.0001,-.0001,0]
        np.testing.assert_array_equal(c.command(Observation(i*.002,(0,0,0),w),.002),reference.command(w,.002))
    assert c.phase=='INSERT' and c.search_count==0 and not c.events
    assert c.config.total_action_time_s==25.
    with pytest.raises(ValueError):c.command(Observation(1,(0,0,0),[0]*6),float('nan'))

def observation_fixture():
    from tools.learning.types import CycleSnapshot
    s=fake_session();s.controller.phase='SEARCH';s.controller.search_origin=np.array([0,0,.0002])
    s.controller.episode_peak_z_m=.0003;s.controller.search_progress_origin_z_m=.0003
    r=dict(position_m=[0,-.00015,-.004],quaternion_wxyz=[1,0,0,0],contact_wrench_M=[0]*6,
        velocity_world=[0]*6,limited_command_world=[0]*6,reference_qpos=[0,-.00015,-.004,1,0,0,0],phase='RUNNING')
    ctrl=s.controller_state_snapshot()
    snap=CycleSnapshot(0,0.,[0]*6,True,r,ctrl)
    context=dict(reason=None,recovery_state=None,recovery_count=0,hold_start=None,wait_start=None,
        actual_stop_start=None,previous_residual=[0]*4,guard_facts=s.env.guard_facts,previous_filter_fraction=1.)
    return s,r,snap,context

def test_v4_observation_is_relative_versioned_idempotent_and_tracks_live_state():
    from tools.learning.v4_observation import V4ObservationBuilder
    s,r,snap,context=observation_fixture();builder=V4ObservationBuilder(r,s.controller.config)
    snap.state=copy.deepcopy(r);snap.state['reference_qpos'][0]=.0001;snap.state['limited_command_world'][0]=.00002
    vec,raw=builder.capture(snap,context,refresh=True)
    assert builder.version=='residual_reference_whitelist_v4'
    assert len(vec)>120 and len(vec)==sum(x['width'] for x in builder.schema)
    assert raw['relative_drive_reference_m']==[.0001,0,0]
    assert raw['previous_limited_command'][0]==.00002
    assert raw['net_search_remaining_m'][0]==pytest.approx(.0004)
    again,_=builder.capture(snap,context);np.testing.assert_array_equal(vec,again)
    assert not any(x in raw for x in ['case_name','hole_position','absolute_error','position_m'])
    # Translating world XY including the initial pose must not change policy.
    shifted=copy.deepcopy(r);shifted['position_m'][0]+=.003;shifted['reference_qpos'][0]+=.003
    other=V4ObservationBuilder(shifted,s.controller.config);moved=copy.deepcopy(snap)
    moved.state['position_m'][0]+=.003;moved.state['reference_qpos'][0]+=.003
    np.testing.assert_allclose(other.capture(moved,context)[0],vec,rtol=0,atol=1e-7)

def test_v4_observation_rejects_nonfinite_new_state():
    from tools.learning.v4_observation import V4ObservationBuilder
    s,r,snap,context=observation_fixture();builder=V4ObservationBuilder(r,s.controller.config)
    snap.controller_state['search_progress_origin_z_m']=float('nan')
    with pytest.raises(ValueError):builder.capture(snap,context)
