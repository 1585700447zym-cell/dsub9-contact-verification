"""Report must distinguish no intervention, early exit and actual restoration."""
import pytest


def test_no_trigger_is_reported_without_inventing_pause():
    from tools.reporting.report_b2_y_probe import execution_profile
    result=execution_profile([], [], .002)
    assert result['triggered'] is False
    assert result['zero_gain_command_duration_s']==0
    assert result['resume_ramp_executed'] is False
    assert result['full_search_restored'] is False


def test_actual_ramp_and_full_restoration_are_separate():
    from tools.reporting.report_b2_y_probe import execution_profile
    events=[{'event':'XY_PROBE_START','time_s':2.}, {'event':'XY_SEARCH_FULLY_RESTORED','time_s':3.1}]
    rows=[{'extra_xy_gain':0.}, {'extra_xy_gain':.5}, {'extra_xy_gain':1.}]
    result=execution_profile(events,rows,.002)
    assert result['zero_gain_command_duration_s']==pytest.approx(.002)
    assert result['resume_ramp_command_duration_s']==pytest.approx(.002)
    assert result['resume_ramp_executed'] is True
    assert result['full_search_restored'] is True


def test_parent_exit_does_not_claim_restoration():
    from tools.reporting.report_b2_y_probe import execution_profile
    events=[{'event':'XY_PROBE_START','time_s':2.}, {'event':'XY_PROBE_ENDED_BY_PARENT','time_s':2.004,'phase':'INSERT'}]
    result=execution_profile(events,[{'extra_xy_gain':0.}]*2,.002)
    assert result['zero_gain_command_duration_s']==pytest.approx(.004)
    assert result['ended_by_parent']['phase']=='INSERT'
    assert result['resume_ramp_executed'] is False
    assert result['full_search_restored'] is False
