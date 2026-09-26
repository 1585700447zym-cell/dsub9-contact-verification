import importlib
import pytest


def checker():
    m=importlib.import_module('tools.validation.measure_readiness_stop')
    assert hasattr(m,'stop_qualified'), 'Final-step invalid states must be checked explicitly'
    return m.stop_qualified


def valid():
    return dict(phase='STOPPING',events=[],recorded_time_s=12.,deadline_s=12.,
                confirmed={'confirmed_after_stop_s':1.5},final_stable=True,
                peaks={'force_N':.01,'torque_G_Nm':.0001,'penetration_m':1e-6})


@pytest.mark.parametrize('reason',['INVALID_SIMULATION','INVALID_PENETRATION','SIMULATION_ERROR','OUT_OF_BOUNDS'])
def test_invalid_final_step_cannot_pass_using_retained_finite_observation(reason):
    f=checker();args=valid();args['events']=[{'reason':reason}]
    assert not f(**args)


def test_terminal_phase_and_missing_endpoint_are_rejected():
    f=checker();args=valid();assert f(**args)
    args['phase']='TERMINAL';assert not f(**args)
    args['phase']='STOPPING';args['recorded_time_s']=11.9998;assert not f(**args)
