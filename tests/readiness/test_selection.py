import importlib
import pytest


def api():
    spec=importlib.util.find_spec('tools.reporting.report_training_readiness')
    assert spec is not None, 'Readiness comparison is missing'
    return importlib.import_module(spec.name)


def metric(case,success=False,advance=0,force=10):
    return {'case':case,'success':success,'termination':'GEOMETRIC_SUCCESS' if success else 'NO_PROGRESS',
            'advance_mm':advance,'success_time_s':5 if success else None,'peak_force_mN':force,
            'peak_torque_mNm':.1,'peak_penetration_um':10}


def test_more_depth_without_task_success_does_not_select_candidate():
    m=api();old=[metric('a',True),metric('b')];new=[metric('a',True),metric('b',advance=3.99)]
    assert m.select_baseline(old,new)['selected']=='B2_original'


def test_more_success_cannot_hide_new_overload():
    m=api();old=[metric('a',True),metric('b'),metric('c')]
    new=[metric('a',True),metric('b',True),metric('c',force=26)]
    assert m.select_baseline(old,new)['selected']=='B2_original'


def test_safe_additional_success_can_select_candidate():
    m=api();old=[metric('a',True),metric('b')];new=[metric('a',True),metric('b',True)]
    assert m.select_baseline(old,new)['selected']=='B2_pause2_candidate'


def test_reproduction_summary_cannot_overwrite_original_delivery():
    with pytest.raises(ValueError,match='output'):
        api().matrix_report('a_new_reproduction')
