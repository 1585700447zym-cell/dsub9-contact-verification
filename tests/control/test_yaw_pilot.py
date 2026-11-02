"""Pure-computation pilot tests: never construct/reset a dynamics environment."""
import math
from types import SimpleNamespace
import numpy as np
import pytest


def api():
    from tools.control import yaw_admittance
    return yaw_admittance


@pytest.mark.parametrize('angle', [1., -1., 1.5, -1.5])
def test_yaw_quaternion_uses_rz_ry_rx(angle):
    from tools.validation.run_contact_cases import _quaternion
    r,p,y = map(math.radians, [-1., 1., angle])
    q = _quaternion(SimpleNamespace(roll_rad=r,pitch_rad=p,yaw_rad=y))
    w,x,a,z = q
    actual = np.array([[1-2*(a*a+z*z),2*(x*a-z*w),2*(x*z+a*w)],
                       [2*(x*a+z*w),1-2*(x*x+z*z),2*(a*z-x*w)],
                       [2*(x*z-a*w),2*(a*z+x*w),1-2*(x*x+a*a)]])
    rx=np.array([[1,0,0],[0,math.cos(r),-math.sin(r)],[0,math.sin(r),math.cos(r)]])
    ry=np.array([[math.cos(p),0,math.sin(p)],[0,1,0],[-math.sin(p),0,math.cos(p)]])
    rz=np.array([[math.cos(y),-math.sin(y),0],[math.sin(y),math.cos(y),0],[0,0,1]])
    np.testing.assert_allclose(actual,rz@ry@rx,atol=1e-15)


def test_absent_yaw_preserves_exact_legacy_quaternion():
    from tools.validation.run_contact_cases import _quaternion
    r,p=.02,-.03
    old=np.array([math.cos(p/2)*math.cos(r/2),math.cos(p/2)*math.sin(r/2),
                  math.sin(p/2)*math.cos(r/2),-math.sin(p/2)*math.sin(r/2)])
    np.testing.assert_array_equal(_quaternion(SimpleNamespace(roll_rad=r,pitch_rad=p)),old)


@pytest.mark.parametrize('value',[float('nan'),float('inf'),True])
def test_invalid_yaw_rejected(value):
    from tools.validation.run_contact_cases import _quaternion
    with pytest.raises(ValueError):
        _quaternion(SimpleNamespace(roll_rad=0.,pitch_rad=0.,yaw_rad=value))


def test_yaw_moment_sign_transient_and_four_axis_unchanged():
    from tools.control.fixed_admittance import FixedAdmittance,AdmittanceConfig
    cfg=AdmittanceConfig(virtual_mass=(20.,20.,.02,.02),damping=(2000.,2000.,1.,1.))
    old=FixedAdmittance(cfg);new=api().YawFixedAdmittance(cfg)
    for moment in (.01,-.01):
        old.reset();new.reset()
        w=[.2,-.1,0.,.002,-.003,moment]
        actual=new.command(w,.002);expected=old.command(w,.002)
        np.testing.assert_array_equal(actual[:5],expected[:5])
        assert actual[5]==pytest.approx(moment*(1-math.exp(-.1)))
        assert new.yaw_offset==pytest.approx(actual[5]*.002)
        assert new.offset.shape==(4,)


def test_yaw_limits_and_reset():
    c=api().YawFixedAdmittance()
    for _ in range(2200):
        command=c.command([0,0,0,0,0,100.],.002)
        assert abs(command[5])<=.02+1e-14
        assert abs(c.yaw_offset)<=.08
    assert command[5]==0.
    c.reset()
    assert c.yaw_offset==c.yaw_velocity==0.


@pytest.mark.parametrize('phase',['INSERT','SEARCH','UNLOAD'])
def test_active_phases_preserve_yaw_exactly_once(phase):
    from tools.control.reference_search import DriveObservation
    c=api().make_yaw_controller();c.phase=phase
    c.search_origin=np.zeros(3);c.search_progress_origin_z_m=0.
    obs=DriveObservation(.1,(0.,0.,0.),(0.,0.,-1.,0.,0.,.01),0.,(0.,0.,0.),(0.,0.))
    result=c.command(obs,.002)
    assert result[5]==pytest.approx(.01*(1-math.exp(-.1)))
    assert c.admittance.yaw_offset==pytest.approx(result[5]*.002)


@pytest.mark.parametrize('phase',['WAIT_RECOVERY','FAILED'])
def test_inactive_phases_do_not_command_or_integrate_yaw(phase):
    from tools.control.reference_search import DriveObservation
    c=api().make_yaw_controller();c.phase=phase
    obs=DriveObservation(.1,(0.,0.,0.),(0.,0.,0.,0.,0.,.01),0.,(0.,0.,0.),(0.,0.))
    np.testing.assert_array_equal(c.command(obs,.002),np.zeros(6))
    assert c.admittance.yaw_offset==0.


def test_only_four_nonzero_cases_and_legacy_case_serialization():
    from dataclasses import asdict
    from tools.validation.yaw_pilot import pilot_cases
    from tools.validation.run_contact_cases import ContactCase
    cases=pilot_cases()
    assert len(cases)==4
    assert [round(math.degrees(c.yaw_rad),5) for c in cases]==[1.,-1.,1.5,-1.5]
    for c in cases:
        assert (c.x_offset_m,c.y_offset_m)==(.0003,.0003)
        assert all(v!=0 for v in (c.x_offset_m,c.y_offset_m,c.roll_rad,c.pitch_rad,c.yaw_rad))
    assert 'yaw_rad' not in asdict(ContactCase.aligned())


def test_yaw_is_array_rotation_not_identical_pin_offsets():
    from tools.validation.yaw_pilot import pin_diagnostics
    q=[math.cos(math.radians(1)/2),0,0,math.sin(math.radians(1)/2)]
    row={'position_m':[.0003,.0003,-.005],'quaternion_wxyz':q}
    pins=pin_diagnostics(row)
    assert len(pins)==9
    assert np.ptp([p['tip_xy_offset_m'][1] for p in pins])>.00019


def test_nine_pin_referee_checks_yaw_geometry():
    from tools.model.layered_task import layered_pin_fit
    for angle,expected in [(0.,True),(1.,True),(1.5,False)]:
        a=math.radians(angle)/2
        row={'position_m':[0.,0.,0.],'quaternion_wxyz':[math.cos(a),0.,0.,math.sin(a)]}
        assert layered_pin_fit(row)==expected


def test_invalid_yaw_reset_closes_previous_observation():
    from tools.validation.yaw_pilot import environment_class
    Env=environment_class()
    env=object.__new__(Env)  # No MjModel/MjData construction or research reset.
    env.phase='RUNNING';env._observation_ready=True
    with pytest.raises(ValueError):env.reset(SimpleNamespace(yaw_rad=math.radians(2.)))
    assert env.phase=='TERMINAL' and env._observation_ready is False
