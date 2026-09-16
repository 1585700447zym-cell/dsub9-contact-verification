import importlib
import math
import numpy as np
import pytest


def api():return importlib.import_module('tools.control.fixed_admittance')


def test_zero_wrench_only_advances_z():
    c=api().FixedAdmittance()
    for _ in range(5):command=c.command(np.zeros(6),.002)
    assert command==pytest.approx([0,0,.001,0,0,0])


def test_force_and_moment_response_has_correct_directions_and_steady_gain():
    c=api().FixedAdmittance()
    for _ in range(1000):v=c.command([.002,-.004,100,.00002,-.00003,100],.002)
    assert v[0]==pytest.approx(.0001,rel=1e-6)
    assert v[1]==pytest.approx(-.0002,rel=1e-6)
    assert v[3]==pytest.approx(.002,rel=1e-6)
    assert v[4]==pytest.approx(-.003,rel=1e-6)
    assert v[2]==.001 and v[5]==0


def test_first_order_transient_matches_independent_solution():
    c=api().FixedAdmittance()
    v=c.command([.002,0,0,0,0,0],.002)
    assert v[0]==pytest.approx(.0001*(1-math.exp(-.2)),rel=1e-10)


def test_bounds_and_reset_prevent_persistent_windup():
    c=api().FixedAdmittance()
    for _ in range(2500):v=c.command([100,0,0,100,0,0],.002)
    assert abs(c.offset[0])<=.0005 and abs(c.offset[2])<=.08
    assert v[0]==0 and v[3]==0
    for _ in range(5):v=c.command([-100,0,0,-100,0,0],.002)
    assert v[0]<0 and v[3]<0
    c.reset();assert np.all(c.offset==0) and np.all(c.velocity==0)


@pytest.mark.parametrize('wrench,dt',[([0]*5,.002),([0,0,np.nan,0,0,0],.002),([0]*6,0)])
def test_invalid_input_rejected(wrench,dt):
    with pytest.raises(ValueError):api().FixedAdmittance().command(wrench,dt)


def test_feedback_disabled_is_exact_zero_feedback_reference():
    c=api().FixedAdmittance(feedback_enabled=False)
    assert c.command([100]*6,.002)==pytest.approx([0,0,.001,0,0,0])
