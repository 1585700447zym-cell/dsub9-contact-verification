"""Catch a feasible first step that leaves the actual next B2 command infeasible."""
import gzip,json,math
from pathlib import Path
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest

ROOT=Path(__file__).resolve().parents[2]

@pytest.fixture(scope='module')
def frozen():
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()
    p=ROOT/'deliverables/task_variants/layered_referee_20261004/run/y_neg_150.json.gz'
    trace=json.loads(gzip.decompress(p.read_bytes()))['trace']
    common=json.loads((ROOT/'deliverables/paper_comparison/protocol_v4_20261004/protocol.json').read_text(encoding='utf8'))['common']
    examples=json.loads((ROOT/'deliverables/paper_comparison/protocol_v4_20261004/residual_integration_audit.json').read_text(encoding='utf8'))['examples']
    return common,trace,examples

def oracle(common,theta,ref,previous):
    from tools.control.reference_search import ReferenceSearchRecovery,DriveSearchConfig,DriveObservation
    from tools.control.search_recovery import SearchConfig
    from tools.control.risk_search import RotationRiskConfig
    from tools.control.load_search import SearchLoadConfig
    from tools.dynamics.safety import limit_command
    c=ReferenceSearchRecovery(SearchConfig(**common['b2_config']),RotationRiskConfig(**common['rotation_risk']),
        SearchLoadConfig(**common['search_load']),DriveSearchConfig(**common['drive_limits']))
    c.phase='SEARCH';c.search_count=1;c.search_origin=np.zeros(3);c.theta=theta
    obs=DriveObservation(1.,(0,0,.0002),(0,0,-.008,0,0,0),(0,0,0),tuple(list(ref)+[0]),tuple(previous[:2]))
    command=c._search_command(obs,.002)
    limited=limit_command(command,previous,.002,[.001]*3+[.03]*3,[.005]*3+[.3]*3)
    return c,limited

def args(common,trace,e):
    from tools.control.search_recovery import SearchConfig
    i=next(i for i,r in enumerate(trace) if abs(r['time_s']-e['command_time_s']-.002)<1e-8)
    cfg=SearchConfig(**common['b2_config']);theta=trace[i]['search_composition']['theta_rad'];b=cfg.spiral_pitch_m/(2*math.pi)
    advanced=min(cfg.spiral_radius_m/b,theta+cfg.spiral_speed_m_s/math.hypot(b*theta,b)*.002)
    return dict(phase='SEARCH',enabled=True,previous_limited=e['previous_limited_command'],dt=.002,
        reference_xy=e['reference_xy_m'],radius=.00012,next_theta=advanced,search_config=cfg)

def test_six_counterexamples_do_not_leave_next_actual_b2_in_reference_failure(frozen):
    from tools.learning.v4_continuation import compose_continuation_command
    common,trace,examples=frozen
    for e in examples:
        a=args(common,trace,e)
        command,log=compose_continuation_command(e['base_command'],e['normalized_action'],**a)
        assert log['next_zero_reference_feasible']
        c,limited=oracle(common,a['next_theta'],log['predicted_reference_xy_m'],log['predicted_limited_command'])
        if log['next_zero_controlled_search_end']:
            assert c.phase=='WAIT_RECOVERY' and c.events[-1]['reference_boundary_end']
        else:
            assert c.phase=='SEARCH' and not c.events
            assert np.linalg.norm(np.array(log['predicted_reference_xy_m'])+limited[:2]*.002)<=.00012+1e-12
            np.testing.assert_allclose(limited[:2],log['next_zero_limited_xy_m_s'],rtol=0,atol=1e-15)
        assert log['experience_action']==e['normalized_action']
        from tools.dynamics.safety import limit_command
        np.testing.assert_array_equal(limit_command(command,a['previous_limited'],.002,[.001]*3+[.03]*3,[.005]*3+[.3]*3),log['predicted_limited_command'])

def test_old_one_step_counterexample_now_ends_search_in_actual_controller(frozen):
    from tools.learning.v4_action import compose_reference_command
    common,trace,examples=frozen;e=examples[0];a=args(common,trace,e)
    _,log=compose_reference_command(e['base_command'],e['normalized_action'],**{k:v for k,v in a.items() if k not in ('next_theta','search_config')})
    c,_=oracle(common,a['next_theta'],log['predicted_reference_xy_m'],log['predicted_limited_command'])
    assert c.phase=='WAIT_RECOVERY' and c.events[-1]['reason']=='SEARCH_EXHAUSTED'
    assert c.events[-1]['reference_boundary_end']

def test_zero_requests_and_disabled_stages_preserve_old_outputs(frozen):
    from tools.learning.v4_continuation import compose_continuation_command
    from tools.learning.v4_action import compose_reference_command
    common,trace,examples=frozen;a=args(common,trace,examples[0])
    for phase,enabled,action in [('SEARCH',True,[0]*4),('INSERT',True,[1]*4),('UNLOAD',False,[1]*4)]:
        a.update(phase=phase,enabled=enabled)
        old,logs=compose_reference_command(examples[0]['base_command'],action,**{k:v for k,v in a.items() if k not in ('next_theta','search_config')})
        new,log=compose_continuation_command(examples[0]['base_command'],action,**a)
        np.testing.assert_array_equal(old,new)
        for k,v in logs.items():assert log[k]==v

def test_final_spiral_segment_is_controlled_end_not_false_reference_failure(frozen):
    from tools.learning.v4_continuation import predict_next_search
    from tools.control.search_recovery import SearchConfig
    common,_,_=frozen;cfg=SearchConfig(**common['b2_config'])
    theta=cfg.spiral_radius_m/(cfg.spiral_pitch_m/(2*math.pi))
    ref=.00012*np.array([math.cos(theta),math.sin(theta)])
    result=predict_next_search(ref,[.0005,.0005],theta,cfg,.002)
    c,_=oracle(common,theta,ref,[.0005,.0005,0,0,0,0])
    assert c.phase in ('WAIT_RECOVERY','FAILED') and c.events[-1].get('reference_boundary_final_segment')
    assert result['controlled_search_end'] and result['reference_feasible']

@pytest.mark.parametrize('theta',[float('nan'),-1.])
def test_invalid_next_theta_cannot_be_silently_accepted(frozen,theta):
    from tools.learning.v4_continuation import compose_continuation_command
    common,trace,examples=frozen;a=args(common,trace,examples[0]);a['next_theta']=theta
    with pytest.raises(ValueError):compose_continuation_command(examples[0]['base_command'],examples[0]['normalized_action'],**a)

def test_infeasible_next_search_baseline_is_reported_as_controlled_end(frozen):
    from tools.learning.v4_continuation import compose_continuation_command
    from tools.learning.v4_action import compose_reference_command
    common,trace,examples=frozen;e=examples[0];a=args(common,trace,e)
    _,old=compose_reference_command(e['base_command'],e['normalized_action'],**{k:v for k,v in a.items() if k not in ('next_theta','search_config')})
    # An angular request cannot repair XY continuation. The common controller
    # must end SEARCH rather than claim its hypothetical next command is valid.
    _,log=compose_continuation_command(old['predicted_limited_command'],[0,0,.1,0],**a)
    assert log['baseline_next_zero_reference_feasible'] and log['next_zero_reference_feasible']
    assert log['next_zero_controlled_search_end'] and not log['continuation_filtered']
    np.testing.assert_array_equal(log['predicted_limited_command'][:2],old['predicted_limited_command'][:2])
    assert log['experience_action']==[0,0,.1,0]

def test_new_session_uses_live_next_theta_and_common_f_s_search_layer(frozen):
    from tools.learning.v4_continuation import ContinuationResidualSession
    from tools.learning.types import CycleSnapshot
    from tools.control.search_recovery import SearchConfig
    from tools.control.reference_search import ReferenceSearchRecovery
    from tools.learning.guarded_environment import LearningEnvironment
    common,trace,examples=frozen;e=examples[0];a=args(common,trace,e);results=[]
    for mode in ('F50','S50'):
        env=object.__new__(LearningEnvironment)
        env.config=SimpleNamespace(control_period=.002,linear_speed=.001,linear_acceleration=.005,angular_speed=.03,angular_acceleration=.3)
        env.reference=np.array(list(e['reference_xy_m'])+[0,1,0,0,0]);env.command=np.array(e['previous_limited_command'])
        s=ContinuationResidualSession(environment=env,mode=mode,controller_factory=lambda:ReferenceSearchRecovery(SearchConfig(**common['b2_config'])))
        s.controller=s.controller_factory();s.controller.theta=a['next_theta'];s.controller.search_origin=np.zeros(3);s.initial=np.zeros(3)
        snap=CycleSnapshot(0,0,e['base_command'],True,{},dict(phase='SEARCH'))
        s._command_for_action(snap,e['normalized_action']);results.append(s.last_action_log)
    assert results[0]==results[1] and results[0]['reference_filter_fraction']<1
    assert not results[0]['continuation_filtered'] and results[0]['next_zero_controlled_search_end']
