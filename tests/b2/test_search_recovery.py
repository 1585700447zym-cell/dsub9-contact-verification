import importlib
import numpy as np
import pytest


def api():return importlib.import_module('tools.control.search_recovery')


def observation(t, p=(0,0,0), fz=0):
    return api().Observation(t,tuple(p),(0,0,fz,0,0,0))


def stalled_controller():
    c=api().SearchRecovery()
    for i in range(302):c.command(observation(i*.002,fz=-.02),.002)
    assert c.phase=='UNLOAD'
    return c


def test_no_contact_does_not_trigger_search():
    c=api().SearchRecovery()
    for i in range(1000):v=c.command(observation(i*.002,p=(0,0,i*2e-6)),.002)
    assert c.phase=='INSERT' and v.tolist()==[0,0,.001,0,0,0]


def test_axial_stall_triggers_unload_without_requiring_zero_rotation():
    c=stalled_controller()
    assert c.command(observation(.604,fz=-.02),.002)[2]<0
    c.command(observation(.606,fz=-.004),.002)
    assert c.phase=='SEARCH' and c.search_count==1


def test_unload_timeout_fails_closed():
    c=stalled_controller()
    v=c.command(observation(1.7,fz=-.02),.002)
    assert c.phase=='FAILED' and c.reason=='UNLOAD_TIMEOUT'
    assert np.all(v==0)


def test_search_budget_and_only_one_retry():
    c=stalled_controller();c.command(observation(.606),.002)
    c.command(observation(9),.002)
    assert c.phase=='WAIT_RECOVERY'
    c.start_recovered_search(observation(10))
    assert c.search_count==2
    v=c.command(observation(19),.002)
    assert c.phase=='FAILED' and c.reason=='SEARCH_BUDGET_EXHAUSTED' and np.all(v==0)
    with pytest.raises(RuntimeError):c.start_recovered_search(observation(20))


def test_actual_search_excursion_is_guarded():
    c=stalled_controller();c.command(observation(.606),.002)
    v=c.command(observation(.608,(.000201,0,0)),.002)
    assert c.phase=='FAILED' and c.reason=='SEARCH_EXCURSION_LIMIT' and np.all(v==0)


def test_unload_does_not_spend_disabled_lateral_budget():
    c=stalled_controller();before=c.admittance.offset[:2].copy()
    for i in range(250):
        v=c.command(api().Observation(.604+i*.002,(0,0,0),(.008,0,-.012,0,0,0)),.002)
        assert np.all(v[:2]==0)
    assert c.admittance.offset[:2]==pytest.approx(before,abs=1e-15)


@pytest.mark.parametrize('key,value',[('force_N',.026),('torque_G_Nm',.00051),('penetration_m',31e-6)])
def test_past_contact_limit_cannot_be_cleared_by_unloading(key,value):
    from types import SimpleNamespace
    from tools.dynamics.cartesian import DynamicConfig
    env=SimpleNamespace(config=DynamicConfig(),peaks={'force_N':0.,'torque_G_Nm':0.,'penetration_m':0.})
    env.peaks[key]=value
    assert api().latched_contact_guard(env)


def test_episode_latches_transient_peak_during_final_stopping():
    from tools.dynamics.cartesian import CartesianEnvironment
    from tools.validation.run_contact_cases import ContactCase
    from tools.validation.run_b2_search import run_search_episode
    env=CartesianEnvironment(segments=32,contacts_enabled=False)
    original_step=env.step
    def inject_stop_peak(command):
        row=original_step(command)
        if env.phase=='STOPPING':env.peaks['force_N']=.026
        return row
    env.step=inject_stop_peak
    result=run_search_episode(env,ContactCase.aligned(),api().SearchRecovery(api().SearchConfig(total_action_time_s=.01,settle_time_s=.02)))
    assert result['termination']=='FORCE_LIMIT'
    assert any(e['reason']=='B2_LATCHED_FORCE_LIMIT' for e in result['events'])
    assert result['recovery_count']==0


def test_search_uses_local_motion_and_force_not_absolute_hole_error():
    a=api().SearchRecovery();b=api().SearchRecovery();shift=np.array([.004,-.003,.01])
    for i in range(800):
        t=i*.002; fz=-.02 if t<.604 else -.004
        va=a.command(observation(t,fz=fz),.002)
        vb=b.command(observation(t,shift,fz),.002)
        assert va==pytest.approx(vb,abs=1e-12)
    assert a.phase==b.phase=='SEARCH'
    assert max(abs(va[:2]))<=a.config.search_xy_component_speed_m_s


def test_resume_requires_completed_recovery_and_preserves_live_state():
    from tools.dynamics.cartesian import CartesianEnvironment
    from tools.validation.run_contact_cases import ContactCase
    env=CartesianEnvironment(segments=32,contacts_enabled=False);env.reset(ContactCase.aligned())
    with pytest.raises(RuntimeError):api().resume_after_recovery(env,200e-6)
    env.stop('B2_SEARCH_EXHAUSTED');env.request_recovery()
    for _ in range(1000):
        env.step(np.zeros(6))
        if env.phase=='STOPPING' and np.linalg.norm(env.observe()['velocity_world'][:3])<1e-6:break
    p=env.data.qpos.copy();v=env.data.qvel.copy();time=env.data.time;peaks=dict(env.peaks)
    api().resume_after_recovery(env,200e-6)
    assert env.phase=='RUNNING' and env.recovery_count==1
    assert np.array_equal(p,env.data.qpos) and np.array_equal(v,env.data.qvel)
    assert time==env.data.time and peaks==env.peaks
    env.stop('FORCE_LIMIT')
    with pytest.raises(RuntimeError):api().resume_after_recovery(env,200e-6)


@pytest.mark.parametrize('field,value',[('spiral_radius_m',float('nan')),('max_searches',3),('search_force_N',.026)])
def test_invalid_configuration_rejected(field,value):
    with pytest.raises(ValueError):api().SearchConfig(**{field:value})
