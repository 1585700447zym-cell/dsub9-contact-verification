"""Native substep stop clock vs cycle-end decision: pure saved mathematics."""
from copy import deepcopy
from importlib import import_module
import pytest


def fixture(lag=.0016,reason='FORCE_LIMIT'):
    start=1.2364;end=3.238;dt=.0002
    samples=[dict(time_s=start+n*dt,linear_m_s=0.,angular_rad_s=0.) for n in range(1,10009)]
    raw=dict(events=[dict(time_s=start,phase='STOPPING',reason=reason)],stop_samples=samples,
             trace=[dict(time_s=end,phase='STOPPING',velocity_world=[0.]*6)])
    return raw,dict(stop_time_s=start+lag,audit_end_time_s=end)


def api():return import_module('tools.validation.native_stop_clock')


def test_valid_substep_guard_preserves_two_second_and_native_tail_requirements():
    raw,receipt=fixture();saved=deepcopy((raw,receipt))
    proof=api().verify_stopping_interval(raw,receipt,.0002,.002)
    assert proof['final_native_samples']==10008
    assert proof['decision_time_s']==receipt['stop_time_s']
    assert proof['decision_lag_s']==pytest.approx(.0016)
    assert (raw,receipt)==saved


@pytest.mark.parametrize('lag,reason',[(-.0002,'FORCE_LIMIT'),(.0022,'FORCE_LIMIT'),(.0016,'TIME_LIMIT')])
def test_misaligned_or_unexplained_decision_clock_is_rejected(lag,reason):
    raw,receipt=fixture(lag,reason)
    with pytest.raises(ValueError):api().verify_stopping_interval(raw,receipt,.0002,.002)


@pytest.mark.parametrize('tamper',['missing_sample','unstable_tail','short_interval'])
def test_actual_stopping_requirements_are_never_relaxed(tamper):
    raw,receipt=fixture()
    if tamper=='missing_sample':raw['stop_samples'].pop(-30)
    elif tamper=='unstable_tail':raw['stop_samples'][-1]['linear_m_s']=.01
    else:receipt['audit_end_time_s']=3.2;raw['trace'][-1]['time_s']=3.2
    with pytest.raises(ValueError,match='STOP_NOT_QUALIFIED'):api().verify_stopping_interval(raw,receipt,.0002,.002)
