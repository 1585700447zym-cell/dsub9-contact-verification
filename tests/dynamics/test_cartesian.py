"""Behavioral checks for real force-driven integration, not pose playback."""
import importlib
from dataclasses import replace
import numpy as np
import pytest
from tools.validation.run_contact_cases import ContactCase, _male_world_wrench


def api():
    return importlib.import_module('tools.dynamics.cartesian')


def test_free_command_moves_gradually_and_stop_removes_velocity():
    env=api().CartesianEnvironment()
    env.reset(ContactCase.separated())
    z=env.data.qpos[2]
    first=env.step([0,0,.001,0,0,0])
    assert 0<first['position_m'][2]-z<.001*.002
    for _ in range(249): row=env.step([0,0,.001,0,0,0])
    assert row['position_m'][2]-z>.00025
    assert row['time_s']==pytest.approx(.5)
    env.stop('TEST_STOP')
    for _ in range(100): row=env.step(np.zeros(6))
    assert np.linalg.norm(row['velocity_world'][:3])<1e-5
    assert max(env.peaks['drive_force_components_N'])<=env.config.force_limit_N+1e-12


def test_contact_wrench_fast_path_matches_contact_sum_and_changes_motion():
    env=api().CartesianEnvironment()
    c=ContactCase.x_offset(100e-6)
    # The explicitly documented exception is for a diagnostic contact-release
    # experiment; the ordinary episode reset must reject this overlap.
    c=replace(c,start_origin_z_m=0,target_depth_m=0)
    with pytest.raises(ValueError): env.reset(c)
    env.reset(c,allow_initial_contact=True)
    direct,_=_male_world_wrench(env.model,env.data,env.male)
    assert env.observe()['contact_wrench_M']==pytest.approx(direct,abs=1e-10)
    x=env.data.qpos[0]
    for _ in range(30): env.step(np.zeros(6))
    assert env.data.qpos[0]<x-1e-6


def test_nonfinite_command_terminates_and_reset_clears_state():
    env=api().CartesianEnvironment();env.reset(ContactCase.separated())
    with pytest.raises(ValueError): env.step([0,0,float('nan'),0,0,0])
    assert env.phase=='TERMINAL'
    with pytest.raises(RuntimeError): env.step(np.zeros(6))
    env.reset(ContactCase.separated())
    assert env.data.time==0 and env.events==[]


def test_solver_nonfinite_output_terminates_before_wrench_conversion(monkeypatch):
    import mujoco
    env=api().CartesianEnvironment();env.reset(ContactCase.separated())
    original=mujoco.mj_forward
    def bad_output(model,data):
        original(model,data)
        data.qfrc_constraint[0]=np.nan
    monkeypatch.setattr(mujoco,'mj_forward',bad_output)
    row=env.step([0,0,.001,0,0,0])
    assert env.phase=='TERMINAL' and env.events[-1]['reason']=='INVALID_SIMULATION'
    assert np.isfinite(row['position_m']).all()
    assert np.all(env.data.qfrc_applied==0)


def test_malformed_command_clears_applied_drive():
    env=api().CartesianEnvironment();env.reset(ContactCase.separated())
    env.step([0,0,.001,0,0,0])
    with pytest.raises(ValueError):env.step(['bad']*6)
    assert env.phase=='TERMINAL' and np.all(env.data.qfrc_applied==0)


def test_recovery_rechecks_live_state():
    env=api().CartesianEnvironment();env.reset(ContactCase.separated());env.stop()
    env.data.qpos[0]=np.nan
    with pytest.raises(RuntimeError):env.request_recovery()
    assert env.phase=='TERMINAL'


def test_near_tangent_step_contact_does_not_report_half_millimetre_overlap():
    import mujoco
    env=api().CartesianEnvironment()
    # Frozen dynamic failure pose: the pin tips exceed the main-bore entrance
    # plane by only nanometres; a 540 um penetration is geometrically impossible.
    env.data.qpos[:]=[9.829955011332662e-5,2.0580398068480773e-7,-.003749996726030722,
                     .9999999999929585,-4.878936777829016e-7,1.3155261512590427e-7,3.71851351932903e-6]
    mujoco.mj_forward(env.model,env.data)
    assert env.data.ncon>0
    assert min(env.data.contact.dist)>-1e-7


def test_recovery_requires_stopped_state_and_retreats():
    env=api().CartesianEnvironment();env.reset(ContactCase.separated())
    with pytest.raises(RuntimeError):env.request_recovery()
    for _ in range(100):env.step([0,0,.001,0,0,0])
    env.stop('TEST_STOP')
    with pytest.raises(RuntimeError):env.request_recovery()
    for _ in range(100):env.step(np.zeros(6))
    z=env.data.qpos[2];env.request_recovery()
    for _ in range(300):env.step(np.zeros(6))
    assert env.data.qpos[2]<z-.00015
    assert env.recovery_count==1


@pytest.mark.parametrize('kwargs',[{'timestep':0},{'timestep':.0003},{'force_limit_N':float('nan')},
                                   {'control_period':-.002}])
def test_invalid_configuration_rejected_before_run(kwargs):
    with pytest.raises(ValueError):api().DynamicConfig(**kwargs)
