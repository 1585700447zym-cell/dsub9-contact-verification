"""Warning protocol over real control hooks with synthetic native sensor rows."""
from dataclasses import replace
from importlib import import_module, util
from types import MethodType, SimpleNamespace
import math

import numpy as np
import pytest

from tests.test_force_recovery_trial import sample


def api():
    assert util.find_spec('tools.learning.load_warning_trial') is not None, 'Warning-only protocol is missing'
    return import_module('tools.learning.load_warning_trial')


def environment(trial=None):
    from tools.learning.guarded_environment import GuardCandidateConfig
    from tools.learning.newton_damping import NewtonProfile
    from tools.learning.newton_profile import dynamic_config
    cls = (trial or api()).environment_class()
    env = object.__new__(cls)
    env.profile = NewtonProfile()
    env.config = replace(dynamic_config(env.profile), recovery_distance_m=.0003)
    env.guard_config = GuardCandidateConfig(math.radians(2.5), math.radians(1.5))
    env._clear_facts(); env._clear_reference_envelope()
    env.phase = 'RUNNING'; env.events = []; env.stop_samples = []
    env.initial = np.array([0., 0., -.004, 1., 0., 0., 0.])
    env.data = SimpleNamespace(time=0., qpos=env.initial.copy(), qvel=np.zeros(6), qfrc_applied=np.zeros(6))
    env.reference = env.initial.copy(); env.command = np.ones(6)*.0001; env.raw_command=env.command.copy()
    env.peaks = dict(force_N=0., torque_G_Nm=0., penetration_m=0.)
    env.cycle_peaks = env.peaks.copy()
    env.recovery_count = 0; env.recovery_start = None; env.stop_snapshot = None
    env.physical_steps = 0; env._observation_ready = True; env._state_valid=lambda:True
    env.observe=MethodType(lambda e: dict(e.last_finite,phase=e.phase),env); env._read=env.observe
    sample(env,0.,0.,check=False)
    return env


def session(env, trial=None):
    s=(trial or api()).session_class()(env)
    s.controller=s.controller_factory()
    s.initial=env.initial[:3].copy(); s.reason=s.stop_time=s.hold_start=None
    s.recovery_state=s.wait_start=None; s.guard_latched=False
    s.done=s.task_finished=False; s.task_end_time=None; s.cycle_id=0
    s._ready=True; s._cache=s._decorated_cache=None; s._features_ready=False
    s.previous_residual=[0.]*5; s.last_action_log={}; s.external_cut=False
    s.case=SimpleNamespace(name='synthetic',target_depth_m=.005)
    return s


def rotate(e, degrees):
    half=math.radians(degrees)/2
    e.data.qpos[3:]=[math.cos(half),0.,0.,math.sin(half)]


def test_sustained_repeated_force_and_combined_rotation_only_warn():
    e=environment(); s=session(e); command=e.command.copy()
    for i in range(1,138):
        rotate(e, 3. if 3<=i<130 else 0.)
        sample(e,i*.0002,7. if i not in (132,133) else 0.)
        if i%10==0: s._post_task_cycle(e.observe())
    assert e.phase=='RUNNING' and not e.events and e.recovery_count==0
    assert s.reason is None and s.recovery_state is None and s.prepare_cycle().residual_enabled
    np.testing.assert_array_equal(e.command,command)
    assert e.guard_facts['contact_reasons']==['FORCE_LIMIT']
    assert e.guard_facts['motion_reasons']==['ROTATION_LIMIT']
    assert not e.active_guard_facts()['motion_reasons'] and not e.active_guard_facts()['contact_reasons']


def test_native_metrics_cover_all_force_exposure_and_separate_task_from_stop_tail():
    e=environment(); s=session(e); s.task_end_time=.0006
    for i,(force,angle) in enumerate([(2.,0.),(5.,0.),(7.,3.),(5.5,3.),(6.5,0.),(.1,0.)],1):
        rotate(e,angle); sample(e,i*.0002,force)
    record=api().receipt_fields(s)['load_warnings']
    assert len(record['samples'])==record['checked_substeps']==6
    assert record['peak_force_N']==7. and record['peak_rotation_rad']==pytest.approx(math.radians(3))
    assert record['metrics']['FORCE_GT5_N']['episodes']==1
    assert record['metrics']['FORCE_GT6_N']['episodes']==2
    assert record['metrics']['ROTATION_GT2P5_DEG']['samples']==2
    assert record['metrics']['FORCE_GT5_N']['excess_integral']==pytest.approx(4*.0002)
    assert record['exposure']['task']['integral_force_Ns']==pytest.approx(14*.0002)
    assert record['exposure']['audit_tail']['square_integral_force_N2s']==pytest.approx((5.5**2+6.5**2+.1**2)*.0002)
    assert record['samples'][0]['reference_z_m']==e.reference[2]


@pytest.mark.parametrize(('kw','reason','category'),[
    ({'torque':.101},'TORQUE_LIMIT','CONTACT_GUARD'),
    ({'penetration':.000031},'PENETRATION_LIMIT','CONTACT_GUARD'),
    ({'speed':.021},'SPEED_LIMIT','MOTION_VIOLATION')])
def test_simultaneous_force_rotation_warning_does_not_waive_other_hard_guard(kw,reason,category):
    e=environment(); s=session(e); rotate(e,3.)
    row=sample(e,.0002,6.1,**kw); s._post_task_cycle(row)
    assert e.phase=='STOPPING' and reason in e.events[0]['reason']
    assert s.adjudicate()['task_outcome']==category and s.reason==category
    with pytest.raises(RuntimeError): e.request_recovery()


def test_invalid_simulation_beats_force_and_rotation_warnings():
    e=environment(); s=session(e); rotate(e,3.); e._state_valid=lambda:False
    s._post_task_cycle(sample(e,.0002,7.))
    assert e.phase=='TERMINAL' and s.adjudicate()['task_outcome']=='INVALID_SIMULATION'


def test_success_holds_geometry_under_instant_and_historical_high_load():
    e=environment(); s=session(e)
    e.data.qpos[:3]=[0.,0.,0.]
    for i in range(1,52):
        row=sample(e,i*.002,7.)
        s._post_task_cycle(row)
    assert s.reason=='GEOMETRIC_SUCCESS' and s.task_finished
    e.data.qpos[0]=.0005
    assert not s.completion_ready(sample(e,.104,7.))


@pytest.mark.parametrize(('actual','allowed'),[(.0002489,False),(.000249,True),(.00025,True)])
def test_normal_recovery_after_warnings_uses_249um_actual_gate(actual,allowed):
    e=environment(); s=session(e); rotate(e,3.); sample(e,.0002,7.)
    e.stop('B2_SEARCH_EXHAUSTED'); sample(e,.002,.1); e.request_recovery()
    e.reference[2]-=.0003; e.data.qpos[2]-=actual
    sample(e,.604,.1); e.stop('RECOVERY_DISTANCE_REACHED')
    if allowed:
        s._resume_after_recovery(); assert e.phase=='RUNNING' and e.recovery_count==1
        assert e.events[-1]['reason']=='B2_RECOVERY_RESUMED'
    else:
        with pytest.raises(RuntimeError): s._resume_after_recovery()


@pytest.mark.parametrize('phase',['RUNNING','RETRACT'])
def test_absolute_native_deadline_stops_even_under_warnings(phase):
    e=environment(); s=session(e); e.phase=phase
    row=sample(e,30.,7.); s._post_task_cycle(row)
    assert e.phase=='STOPPING' and s.reason=='TIME_LIMIT'


def test_warning_flags_do_not_remove_residual_permission_or_clear_guard_history():
    from tools.learning.five_axis_contract import permission
    e=environment(); s=session(e); rotate(e,3.); sample(e,.002,7.)
    s.observations=api().LoadWarningObservation(e.observe(),s.controller.config,e.profile,e)
    s._features_ready=True
    assert permission(s.prepare_cycle().policy_observation)
    assert e.guard_facts['contact_reasons']==['FORCE_LIMIT'] and e.guard_facts['motion_reasons']==['ROTATION_LIMIT']


def test_protocol_only_accepts_900_and_reports_actual_recovery_settings():
    m=api(); contract=m.protocol_config()
    assert contract['task_deadline_s']==30. and contract['passive_yaw_enabled']
    assert contract['task_referee']=='dsub9_clearance120_layered_nano100_v6'
    assert contract['controller_config']['recovery_min_actual_m']==pytest.approx(.000249)
    assert contract['load_warning']['recovery_reference_target_m']==.0003
    assert contract['version']!=m.previous.VERSION and contract['observation_version']==m.OBSERVATION_VERSION
    with pytest.raises(ValueError): m.protocol_config(450)


def test_nonfinite_derived_norm_is_invalid_even_when_components_are_finite():
    e=environment()
    with np.errstate(over='ignore'):
        sample(e,.0002,1e300)
    assert e.phase=='TERMINAL' and not e.guard_facts['simulation_valid']


@pytest.mark.parametrize('search_reference',[False,True])
def test_both_native_step_loops_continue_command_under_force_and_rotation_warnings(monkeypatch,search_reference):
    from tests import test_force_recovery_trial as stub
    monkeypatch.setattr(stub,'environment',environment)
    e=stub.drive_stub(monkeypatch,force_at=lambda t:7.)
    rotate(e,3.); initial=e.data.qpos.copy()
    if search_reference: e.configure_search_envelope([0.,0.],.0004)
    row=e.step([0.,0.,.0005,0.,0.,0.])
    assert row['time_s']==pytest.approx(.002) and e.phase=='RUNNING'
    assert e.data.qpos[2]-initial[2]==pytest.approx(2e-8,abs=1e-15)
    assert e.guard_facts['checked_substeps']==len(e.warning_samples)==10 and not e.events
    assert e.guard_facts['motion_reasons']==['ROTATION_LIMIT']
    assert e.guard_facts['contact_reasons']==['FORCE_LIMIT']


@pytest.mark.parametrize('search_authority', [False, True])
def test_normal_recovery_after_warnings_executes_next_real_session_search_cycle(monkeypatch, search_authority):
    from tests import test_force_recovery_trial as stub
    from tools.learning.newton_profile import NewtonReward
    from tools.learning.recovery_learning_contract import trial_module

    trial = trial_module('load_warning_7pct') if search_authority else api()
    monkeypatch.setattr(stub,'environment',lambda: environment(trial))
    e=stub.drive_stub(monkeypatch,force_at=lambda t:.1)
    s=session(e, trial); s.clipped_duration_s=0.; s.reward=NewtonReward(.005,e.profile)
    rotate(e,3.); sample(e,.0002,7.)
    s.controller.search_count=4
    s.controller._transition('WAIT_RECOVERY',s.policy_observation(e.observe()),'SEARCH_EXHAUSTED')
    e.stop('B2_SEARCH_EXHAUSTED'); s.recovery_state='WAIT_STOP'; s.wait_start=.0002
    sample(e,.002,.1); s.prepare_cycle()
    assert e.phase=='RETRACT'
    e.reference[2]-=.0003; e.data.qpos[2]-=.000249
    sample(e,.604,.1); e.stop('RECOVERY_DISTANCE_REACHED')
    s._post_task_cycle(e.observe()); s._cache=None
    snap=s.prepare_cycle()
    assert snap.residual_enabled and s.controller.phase=='SEARCH' and s.controller.search_count==5
    result=s.advance_cycle(np.ones(5))
    assert result.trace_row['policy_phase']=='SEARCH' and result.trace_row['phase']=='RUNNING'
    assert result.dt==pytest.approx(.002) and e.events[-1]['reason']=='B2_RECOVERY_RESUMED'
    assert s.last_action_log['requested_residual'][:2] == [(.00075 if search_authority else .0005)]*2
    np.testing.assert_allclose(e.command, s.last_action_log['predicted_limited_command'], atol=1e-15)


def test_ordinary_recovery_still_denies_current_high_load_and_unverified_stop_history():
    e=environment(); s=session(e); sample(e,.0002,7.); e.stop('B2_SEARCH_EXHAUSTED')
    assert not s._stable_for_recovery()
    with pytest.raises(RuntimeError): e.request_recovery()
    sample(e,.002,.1); e.request_recovery()
    e.data.qpos[2]-=.0003; sample(e,.604,.1); e.stop('RECOVERY_DISTANCE_REACHED')
    e.events.insert(0,dict(time_s=0.,phase='STOPPING',reason='UNKNOWN_STOP'))
    with pytest.raises(RuntimeError): s._resume_after_recovery()


@pytest.mark.parametrize('decision',[.604,1.606])
def test_failed_normal_resume_marks_final_audit_from_decision_with_any_positive_lag(decision):
    from tools.validation.native313_matrix_audit import actual_stop_start
    e=environment(); s=session(e)
    sample(e,.0002,.1); e.stop('B2_SEARCH_EXHAUSTED')
    sample(e,.002,.1); e.request_recovery()
    e.data.qpos[2]-=.0002489
    sample(e,.6038,.1); e.stop('RECOVERY_DISTANCE_REACHED')
    s.recovery_state='WAIT_RESUME'; s.wait_start=.6038
    sample(e,decision,.1); s.prepare_cycle()
    assert s.reason=='RECOVERY_RESUME_REJECTED'
    assert e.events[-2]['reason']=='RECOVERY_DISTANCE_REACHED'
    marker=e.events[-1]
    assert marker['reason']=='RECOVERY_FINAL_AUDIT_START'
    assert marker['physical_stop_time_s']==.6038 and marker['time_s']==decision
    assert actual_stop_start(e.events,s.stop_time)==decision


def test_native_hard_stop_during_retraction_keeps_its_original_stop_clock():
    from tools.validation.native313_matrix_audit import actual_stop_start
    e=environment(); s=session(e)
    sample(e,.0002,.1); e.stop('B2_SEARCH_EXHAUSTED')
    sample(e,.002,.1); e.request_recovery(); s.recovery_state='RETRACT'
    sample(e,.6038,.1,torque=.101); s._post_task_cycle(sample(e,.604,.1))
    assert s.reason=='CONTACT_GUARD' and actual_stop_start(e.events,s.stop_time)==.6038
    assert all(evt['reason']!='RECOVERY_FINAL_AUDIT_START' for evt in e.events)


@pytest.mark.parametrize('mode', ['mlp', 'gru'])
def test_search_authority_profile_binds_config_composition_and_native_limit(monkeypatch, mode):
    from tests import test_force_recovery_trial as stub
    from tools.learning.global_residual_action import compose_command, recompose_logged_command
    from tools.learning.recovery_learning_contract import (
        experiment_config, trial_module, validate_config, verify_training_registration,
    )

    trial = trial_module('load_warning_7pct')
    config = experiment_config(mode, physical_protocol='load_warning_7pct')
    assert validate_config(config) == config
    contract = trial.protocol_config()
    assert config['physical_protocol']['search_authority'] == contract['search_authority'] == {
        'search_xy_residual_m_s': .00075, 'search_xy_acceleration_m_s2': .020,
    }
    assert contract['search_xy_limit_m_s'] == .0009
    assert contract['task_deadline_s'] == 30. and contract['passive_yaw_enabled']
    with pytest.raises(ValueError, match='new dynamic training qualification'):
        verify_training_registration({}, {}, config=config, qualification_path=None, expected_digest=None)

    monkeypatch.setattr(stub, 'environment', lambda: environment(trial))
    e = stub.drive_stub(monkeypatch, force_at=lambda t: .1)
    s = trial.session_class()(e)
    assert s.contract == contract
    assert s.controller_factory().drive_config.linear_acceleration_m_s2 == .020

    action = [1., -1., 1., -1., 1.]
    for phase, scale, delta in [('SEARCH', .00075, .00004), ('INSERT', .0005, .00001)]:
        e.command[:] = 0.
        e.configure_search_envelope([0., 0.] if phase == 'SEARCH' else None,
                                    .0004 if phase == 'SEARCH' else None)
        command, log = compose_command(np.zeros(6), action, profile='G1', phase=phase, enabled=True,
            previous_limited=e.command.copy(), dt=.002, reference_xy=[0., 0.],
            search_xy_limit_m_s=.0009, **contract['search_authority'])
        _, checked = recompose_logged_command(log, search_xy_limit_m_s=.0009,
                                               **contract['search_authority'])
        assert checked == log
        assert log['requested_residual'] == [scale, -scale, 0., .0005, -.0005, .005]
        e.step(command)
        np.testing.assert_allclose(e.command, [delta, -delta, 0., .0005, -.0005, .0006], atol=1e-15)
        np.testing.assert_allclose(e.command, log['predicted_limited_command'], atol=1e-15)
        np.testing.assert_allclose(e.acceleration_limits, [.005]*3+[.3]*3, atol=1e-15)
