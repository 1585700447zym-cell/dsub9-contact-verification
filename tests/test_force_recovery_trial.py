"""Native hooks and the real session over synthetic sensors; no physics reset."""
from importlib import import_module, util
from types import SimpleNamespace, MethodType
import numpy as np
import pytest


def api():
    assert util.find_spec('tools.learning.force_recovery_trial') is not None, 'Force recovery protocol is missing'
    return import_module('tools.learning.force_recovery_trial')


def environment():
    from tools.learning.newton_damping import NewtonProfile
    from tools.learning.newton_profile import dynamic_config
    from tools.learning.guarded_environment import GuardCandidateConfig
    cls = api().environment_class()
    env = object.__new__(cls)
    env.profile = NewtonProfile(); env.config = dynamic_config(env.profile)
    env.guard_config = GuardCandidateConfig(.1, .1)
    env._clear_facts(); env._clear_reference_envelope()
    env.phase = 'RUNNING'; env.events = []; env.stop_samples = []
    env.initial = np.array([0., 0., -.004, 1., 0., 0., 0.])
    env.data = SimpleNamespace(time=0., qpos=env.initial.copy(), qvel=np.zeros(6), qfrc_applied=np.zeros(6))
    env.reference = env.initial.copy(); env.reference[2] += .0001
    env.command = np.ones(6)*.0001; env.raw_command = env.command.copy()
    env.peaks = dict(force_N=0., torque_G_Nm=0., penetration_m=0.)
    env.cycle_peaks = dict(force_N=0., torque_G_Nm=0., penetration_m=0.)
    env.recovery_count = 0; env.recovery_start = None; env.stop_snapshot = None
    env.physical_steps = 0; env._observation_ready = True
    env._state_valid = lambda: True
    env.observe = MethodType(lambda e: dict(e.last_finite, phase=e.phase), env)
    env._read = env.observe
    sample(env, 0., 0., check=False)
    return env


def sample(env, time, force, *, torque=0., penetration=0., speed=0., check=True):
    env.data.time = time
    row = dict(time_s=time, position_m=env.data.qpos[:3].tolist(), quaternion_wxyz=env.data.qpos[3:].tolist(),
        velocity_world=[speed, 0., 0., 0., 0., 0.], contact_wrench_M=[0., 0., -force, 0., 0., 0.],
        contact_wrench_G=[0., 0., -force, torque, 0., 0.], penetration_m=penetration,
        phase=env.phase, contact_count=1, reference_qpos=env.reference.tolist(),
        limited_command_world=env.command.tolist(), raw_command_world=env.raw_command.tolist())
    env.last_finite = row
    for key, value in [('force_N',force),('torque_G_Nm',torque),('penetration_m',penetration)]:
        env.peaks[key] = max(env.peaks[key], value)
        env.cycle_peaks[key] = value
    if check: env._guard(row)
    return env.observe()


def stable_samples(env, start, duration=.1):
    for index in range(round(duration/.0002)+1):
        sample(env, start+index*.0002, .4)


def session(env=None):
    env = env or environment()
    s = api().session_class()(env)
    s.controller = api().make_controller(env.profile)
    s.initial = env.initial[:3].copy()
    s.case = SimpleNamespace(name='synthetic', target_depth_m=.005)
    s.seed = 1; s.reason = s.stop_time = s.hold_start = None
    s.recovery_state = s.wait_start = None; s.guard_latched = False
    s.done = s.task_finished = False; s.task_end_time = None; s.cycle_id = 0
    s._ready = True; s._cache = s._decorated_cache = None
    s.previous_residual = [0.]*5; s.last_action_log = {}; s.external_cut = False
    s._features_ready = False
    s.observations = api().ForceRecoveryObservation(env.observe(), s.controller.config, env.profile, env)
    return s


def complete_recovery(env):
    sample(env, .0004, 5.5)
    stable_samples(env, .0006)
    env.request_recovery()
    env.data.qpos[2] -= .00025
    sample(env, .6006, .4)
    stable_samples(env, .6008)
    env.resume_force_recovery()


def test_force_trigger_freezes_reference_at_native_time_without_clearing_facts():
    e = environment(); sample(e, .0004, 5.5)
    assert e.phase == 'STOPPING'
    np.testing.assert_array_equal(e.reference, e.data.qpos)
    np.testing.assert_array_equal(e.command, np.zeros(6))
    np.testing.assert_array_equal(e.raw_command, np.zeros(6))
    assert e.guard_facts['contact_reasons'] == ['FORCE_LIMIT']
    assert e.force_recovery_evidence()['events'][0]['trigger_time_s'] == .0004
    s = session(e); e.data.time = .002; e.last_finite['time_s'] = .002
    s._post_task_cycle(e.observe())
    assert s.reason is None and s.recovery_state == 'WAIT_STOP'
    assert s.wait_start == .0004 and s.controller.phase == 'WAIT_RECOVERY'


@pytest.mark.parametrize('force,kwargs', [(6.0001,{}),(5.5,{'torque':.1001}),
    (5.5,{'penetration':30.001e-6}),(5.5,{'speed':.0201})])
def test_force_with_fatal_ceiling_or_other_guard_cannot_recover(force, kwargs):
    e = environment(); sample(e, .0004, force, **kwargs)
    assert not e.recovery_guard_clear()
    with pytest.raises(RuntimeError): e.request_recovery()
    s = session(e); s._post_task_cycle(e.observe())
    assert s.reason in ('CONTACT_GUARD', 'MOTION_VIOLATION')


def test_continuous_force_uses_native_20ms_boundary_and_recurrence_is_fatal():
    e = environment(); sample(e, .0004, 6.)
    sample(e, .0204, 5.1)
    assert not e.force_recovery_evidence()['fatal_reasons']
    sample(e, .0206, 5.1)
    assert 'FORCE_PERSISTENT' in e.force_recovery_evidence()['fatal_reasons']
    other = environment(); sample(other, .0004, 5.5); sample(other, .0006, 4.9); sample(other, .0008, 5.01)
    assert 'FORCE_RECURRENCE' in other.force_recovery_evidence()['fatal_reasons']


def test_force_recovery_requires_continuous_native_100ms_stability():
    e = environment(); sample(e, .0004, 5.5)
    stable_samples(e, .0006, .0998)
    with pytest.raises(RuntimeError): e.request_recovery()
    sample(e, .1006, .4, speed=2e-5)
    stable_samples(e, .1008, .0998)
    with pytest.raises(RuntimeError): e.request_recovery()
    sample(e, .2008, .4); e.request_recovery()
    assert e.phase == 'RETRACT' and e.recovery_count == 1


def test_actual_not_reference_250um_controls_retraction_then_restarts_search():
    e = environment(); s = session(e)
    sample(e, .0004, 5.5); s._post_task_cycle(e.observe()); stable_samples(e, .0006)
    s._cache = None; s.prepare_cycle(); assert e.phase == 'RETRACT'
    e.reference[2] -= .0003; e.data.qpos[2] -= .000249
    e.stop('RECOVERY_DISTANCE_REACHED'); assert e.phase == 'RETRACT'
    e.data.qpos[2] -= .000001; row = sample(e, .6006, .4)
    s._post_task_cycle(row); assert s.recovery_state == 'WAIT_RESUME'
    stable_samples(e, .6008); s._cache = None
    snap = s.prepare_cycle()
    assert e.phase == 'RUNNING' and s.controller.phase == 'SEARCH' and s.reason is None
    assert snap.residual_enabled and e.peaks['force_N'] == 5.5
    assert e.guard_facts['contact_reasons'] == ['FORCE_LIMIT']
    assert e.force_recovery_evidence()['events'][0]['status'] == 'COMPLETED'


@pytest.mark.parametrize('state', ['UNLOADING','RETRACT','WAIT_RESUME'])
def test_native_deadline_aborts_all_recovery_phases_without_reset(state):
    e = environment(); sample(e, .0004, 5.5)
    if state != 'UNLOADING':
        stable_samples(e, .0006); e.request_recovery()
    if state == 'WAIT_RESUME':
        e.data.qpos[2] -= .00025; sample(e, .6006, .4)
    sample(e, 30., .4)
    s = session(e); s.recovery_state = 'RETRACT' if state == 'RETRACT' else 'WAIT_STOP'
    snap = s.prepare_cycle()
    assert s.reason == 'TIME_LIMIT' and not snap.residual_enabled
    assert e.data.time == 30. and e.phase == 'STOPPING'
    assert e.force_recovery_evidence()['events'][0]['status'] == 'ABORTED'
    with pytest.raises(RuntimeError): e.request_recovery()


def test_recovered_history_is_honest_but_does_not_disable_active_observation_or_success():
    from tools.learning.five_axis_contract import permission
    e = environment(); complete_recovery(e)
    s = session(e); s._features_ready = True
    snap = s.prepare_cycle()
    assert permission(snap.policy_observation) and e.guard_facts['contact_reasons'] == ['FORCE_LIMIT']
    assert s._finish_peaks_ok(e.observe())
    s._post_task_cycle(e.observe()); assert s.reason is None
    sample(e, .701, 5.2)
    assert not s._finish_peaks_ok(e.observe())


def test_completed_force_recovery_does_not_waive_stop_tail_recurrence():
    e = environment(); complete_recovery(e)
    s = session(e); s.task_finished = True; s.reason = 'GEOMETRIC_SUCCESS'
    e.stop('TARGET_PLANE_REACHED'); sample(e, .701, 5.2)
    out = s.adjudicate()
    assert out['task_outcome'] != 'FULL_SUCCESS'
    assert out['had_force_recovery'] and out['force_recovery_fatal_reasons']


def test_protocol_is_opt_in_and_uses_active_referee():
    from tools.learning.time_budget_trial import protocol_config as old
    from tools.model.layered_task import TASK_ID
    new = api().protocol_config(900)
    assert new['version'] != old(900)['version'] and new['task_referee'] == TASK_ID
    assert new['task_deadline_s'] == 30. and new['optimizer_updates'] == 0
    assert new['passive_yaw_enabled'] and new['force_recovery']['fatal_force_N'] == 6.


def test_aborted_recovery_keeps_final_contact_guard_classification():
    e = environment(); s = session(e)
    sample(e,.0004,5.5); s._post_task_cycle(e.observe())
    e.data.time = 1.002; e.last_finite['time_s'] = 1.002
    s._finish('RECOVERY_NOT_STABLE')
    assert s.reason == 'RECOVERY_NOT_STABLE'
    assert s.adjudicate()['task_outcome'] == 'CONTACT_GUARD'
    from tools.validation.native313_matrix_audit import actual_stop_start
    assert actual_stop_start(e.events,s.stop_time) == 1.002


def test_unexplained_historical_peak_is_never_waived():
    e = environment(); e.peaks['force_N'] = 5.3
    s = session(e)
    assert not e.recovery_guard_clear()
    assert not s._finish_peaks_ok(e.observe())


def test_native_contiguous_runtime_ledger_passes_independent_audit():
    from tools.validation.force_recovery_audit import verify_recovery_evidence
    e = environment(); cycle_peaks=[]; cycle_peak=0.
    for index in range(1,3511):
        now=index*.0002
        if e.phase=='RETRACT': e.data.qpos[2] -= .0000001
        force=5.5 if index==2 else .4
        sample(e,now,force)
        cycle_peak=max(cycle_peak,force)
        if index%10==0:
            cycle_peaks.append(dict(force_N=cycle_peak)); cycle_peak=0.
            if e.active_force_recovery and e.force_recovery_stable():
                if e.active_force_recovery['status']=='UNLOADING': e.request_recovery()
                elif e.active_force_recovery['status']=='WAIT_RESUME': e.resume_force_recovery()
    proof=verify_recovery_evidence(e.force_recovery_evidence(),cycle_peaks=cycle_peaks,
        facts=e.guard_facts,end_time_s=e.data.time)
    assert proof['all_force_events_recovered']


def test_completed_force_history_allows_normal_recovery_and_load_release():
    e = environment(); complete_recovery(e)
    s = session(e); snap=s.prepare_cycle()
    s.controller.phase='UNLOAD'; s.controller.search_count=3
    s.controller.reference_release_requested=True
    snap.controller_state['phase']='UNLOAD'; snap.base_command=[0.]*6; snap.residual_enabled=False
    s._command_for_action(snap,np.zeros(5))
    assert not s.controller.reference_release_requested
    e.stop('B2_SEARCH_EXHAUSTED'); e.request_recovery()
    e.data.qpos[2] -= .00025; sample(e,1.3,.4); e.stop('RECOVERY_DISTANCE_REACHED')
    e.resume_force_recovery()
    assert e.phase=='RUNNING' and e.recovery_count==2
    assert e.guard_facts['contact_reasons']==['FORCE_LIMIT'] and len(e.events)==8


def test_completed_force_history_does_not_accept_unknown_stop_event():
    e=environment(); complete_recovery(e)
    e.stop('OTHER_STOP'); e.request_recovery()
    e.data.qpos[2] -= .00025; sample(e,1.3,.4); e.stop('RECOVERY_DISTANCE_REACHED')
    with pytest.raises(RuntimeError,match='unverified stop'): e.resume_force_recovery()


def test_first_force_after_other_fatal_guard_is_recorded_without_recovery():
    e=environment(); sample(e,.0002,1.,torque=.101)
    sample(e,.0004,5.2)
    evidence=e.force_recovery_evidence()
    assert len(evidence['events'])==1 and evidence['events'][0]['status']=='FATAL'
    assert any(event['reason']=='FORCE_LIMIT' and event['time_s']==.0004 for event in e.events)
    assert evidence['samples'][0]['force_N']==5.2 and not e.recovery_guard_clear()
    sample(e,.0006,5.3)
    assert len(e.force_recovery_events)==1
    with pytest.raises(RuntimeError): e.request_recovery()


def test_error_collector_preserves_nonfinite_force_evidence_as_json_tags(monkeypatch):
    import json
    from tools.learning import five_axis_collection
    e=environment(); sample(e,.0004,5.5); e.force_recovery_samples[-1]['linear_m_s']=float('nan')
    s=session(e)
    def failed(*args,**kwargs):
        raise five_axis_collection.CollectionError('invalid sensor',dict(evidence={}))
    monkeypatch.setattr(five_axis_collection,'collect_episode',failed)
    with pytest.raises(five_axis_collection.CollectionError) as caught:
        api().collect_episode(s,None,policy=None)
    encoded=json.dumps(caught.value.archive,allow_nan=False)
    assert 'nonfinite' in encoded and 'invalid sensor' == str(caught.value)


def drive_stub(monkeypatch, *, force_at):
    """Keep both actual production step loops; replace only MuJoCo primitives."""
    import mujoco
    e=environment(); e.model=object(); e.male=0; e.grasp_local=np.zeros(3)
    e.data.xmat=np.eye(3).reshape(1,9); e.data.xpos=e.data.qpos[:3][None].copy()
    e.kp=e.kd=np.ones(6); e.drive=np.zeros(6)
    e.velocity_limits=np.array([.001]*3+[.03]*3)
    e.acceleration_limits=np.array([.005]*3+[.3]*3)
    e.effort_limits=np.array([8.]*3+[.2]*3)
    e.command_limited_steps=e.reference_limited_steps=e.drive_saturation_steps=0
    e.first_contact=None
    e.peaks.update(speed_m_s=0.,contact_count=0,drive_force_components_N=[0.]*3,
                   drive_torque_components_Nm=[0.]*3)
    e.command[:]=0.; e.begin_cycle()
    e._read=MethodType(lambda env: sample(env,env.data.time,force_at(env.data.time),check=False),e)
    def integrate(model,q,velocity,dt): q[:3] += np.asarray(velocity)[:3]*dt
    def difference(model,out,dt,a,b): out[:]=0.; out[:3]=(b[:3]-a[:3])/dt
    def step(model,data):
        data.time += .0002; data.qpos[:3] += e.command[:3]*.0002; data.qvel[:]=e.command
    monkeypatch.setattr(mujoco,'mju_quat2Mat',lambda out,q: out.__setitem__(slice(None),np.eye(3).ravel()))
    monkeypatch.setattr(mujoco,'mj_integratePos',integrate)
    monkeypatch.setattr(mujoco,'mj_differentiatePos',difference)
    monkeypatch.setattr(mujoco,'mj_applyFT',lambda *args: None)
    monkeypatch.setattr(mujoco,'mj_step',step)
    monkeypatch.setattr(mujoco,'mj_forward',lambda model,data: data.xpos.__setitem__(0,data.qpos[:3]))
    return e


@pytest.mark.parametrize('armed',[False,True])
def test_both_production_native_loops_stop_at_trigger_before_cycle_end(monkeypatch,armed):
    e=drive_stub(monkeypatch,force_at=lambda t: 5.5 if abs(t-.0004)<1e-10 else .4)
    if armed: e.configure_search_envelope([0.,0.],.0004)
    initial=e.data.qpos.copy(); row=e.step([0.,0.,.0005,0.,0.,0.])
    assert e.physical_steps==10 and e.guard_facts['checked_substeps']==10
    assert row['time_s']==pytest.approx(.002) and e.events[0]['time_s']==pytest.approx(.0004)
    assert e.phase=='STOPPING' and e.data.qpos[2]-initial[2]==pytest.approx(4e-9,abs=1e-15)
    np.testing.assert_array_equal(e.reference,e.data.qpos)
    np.testing.assert_array_equal(e.command,np.zeros(6))


def test_native_deadline_stops_retraction_inside_production_loop(monkeypatch):
    e=drive_stub(monkeypatch,force_at=lambda t:.4)
    e.phase='RETRACT'; e.data.time=29.998; e.recovery_start=e.data.qpos.copy()
    e.recovery_start_time=29.998
    e.step([0.]*6)
    assert e.phase=='STOPPING' and e.events[-1]['reason']=='TIME_LIMIT'
    assert e.events[-1]['time_s']==pytest.approx(30.,abs=1e-10)
    stopped=e.data.qpos.copy(); e.step([0.,0.,-.0005,0.,0.,0.])
    np.testing.assert_array_equal(e.data.qpos,stopped)


def test_without_a_recovered_event_success_keeps_original_strict_peak_limit():
    e=environment(); e.peaks['force_N']=5.
    assert not session(e)._finish_peaks_ok(e.observe())


@pytest.mark.parametrize('name,value',[('stop_force_N',5.1),('recovery_speed',.0006),('timestep',.0001)])
def test_protocol_rejects_unregistered_physical_recovery_settings(name,value):
    from dataclasses import replace
    e=environment(); e.config=replace(e.config,**{name:value})
    with pytest.raises(ValueError,match='force recovery settings'):
        api().session_class()(e)


def test_configuration_entry_prints_both_groups_without_constructing_environment(monkeypatch,capsys):
    import json,runpy,sys
    from tools.learning import time_budget_trial
    def forbidden(): raise AssertionError('Configuration must not construct an environment')
    monkeypatch.setattr(time_budget_trial,'environment_class',forbidden)
    monkeypatch.delitem(sys.modules,'tools.learning.force_recovery_trial',raising=False)
    runpy.run_module('tools.learning.force_recovery_trial',run_name='__main__')
    output=capsys.readouterr().out
    assert output, 'Configuration-only command is missing'
    record=json.loads(output)
    assert record['configuration_only'] and [g['group'] for g in record['groups']]==['search_450','search_900']


@pytest.mark.parametrize('preceding_force',[False,True])
def test_normal_recovery_keeps_legacy_200um_actual_resume_rule(preceding_force):
    e=environment()
    if preceding_force: complete_recovery(e)
    e.stop('B2_SEARCH_EXHAUSTED'); e.request_recovery()
    e.data.qpos[2] -= .00021
    sample(e,1.3,.4); e.stop('RECOVERY_DISTANCE_REACHED')
    assert e.phase=='STOPPING'
    e.resume_force_recovery()
    assert e.phase=='RUNNING'
