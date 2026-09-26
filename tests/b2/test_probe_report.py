"""Negative trials must remain reportable without inventing missing time."""
import pytest
from tools.reporting.report_b2_xy_probe import window


def record(end=1., stopped=False):
    return {'case':{'start_origin_z_m':0.}, 'trace':[
        {'time_s':i*.2,'position_m':[i*1e-6,0.,i*2e-6],
         'phase':'STOPPING' if stopped and i>=2 else 'RUNNING'}
        for i in range(round(end/.2)+1)]}


def test_complete_window_can_include_protective_stopping():
    result=window(record(stopped=True),0.,1.)
    assert result['complete_window'] and result['contains_nonrunning']
    assert result['advance_um']==pytest.approx(10.)


def test_early_termination_reports_missing_window_instead_of_asserting():
    result=window(record(end=.4),0.,1.)
    assert not result['complete_window']
    assert result['available_duration_s']==pytest.approx(.4)
    assert result['advance_um'] is None and result['xy_path_um'] is None
    assert result['observed_advance_um']==pytest.approx(4.)
