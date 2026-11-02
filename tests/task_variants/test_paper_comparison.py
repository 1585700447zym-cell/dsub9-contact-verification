import json
from pathlib import Path
import pytest

from tools.evaluation.paper_comparison import comparison_key, summarize, compare


def row(case='a', success=True):
    return dict(case_id=case, comparison_key='common-v4', outcome='FULL_SUCCESS' if success else 'TASK_FAILURE',
                status='finished', simulation_valid=True, physical_stopped=True, guard_reasons=[],
                contact_guard=False, motion_violation=False,
                task_end_time_s=5., physical_end_time_s=7., peak_force_N=.01, peak_torque_Nm=.0001,
                strict_precision_success=success, sampled_force_integral_N_s=.02)


def test_fingerprint_stable_and_sensitive():
    assert comparison_key({'a':1,'b':2})==comparison_key({'b':2,'a':1})
    assert comparison_key({'a':1})!=comparison_key({'a':2})
    with pytest.raises(ValueError):comparison_key({'a':float('nan')})


def test_failures_remain_in_denominator_and_penalized_time():
    result=summarize([row(),row('b',False)],['a','b'])
    assert result['success_rate']==.5
    assert result['mean_penalized_time_s']==15.5
    assert result['mean_success_time_s']==5.
    assert result['comparison_eligible']


def test_no_success_has_null_success_time():
    result=summarize([row(success=False)],['a'])
    assert result['mean_success_time_s'] is None
    assert result['mean_penalized_time_s']==26.


def test_unfinished_attempt_is_not_dropped():
    r=dict(case_id='b',comparison_key='common-v4',status='error')
    result=summarize([row(),r],['a','b'])
    assert result['attempts']==2 and result['success_rate']==.5
    assert result['mean_penalized_time_s']==15.5
    assert result['unassessed_attempts']==1
    assert not result['comparison_eligible']
    assert result['mean_peak_force_N'] is None


def test_missing_case_does_not_yield_complete_matrix():
    result=summarize([row()],['a','b'])
    assert result['missing_cases']==['b'] and not result['comparison_eligible']


@pytest.mark.parametrize('change',[{'simulation_valid':False,'outcome':'INVALID_SIMULATION'},
                                   {'physical_stopped':False,'outcome':'STOP_NOT_QUALIFIED'}])
def test_invalid_or_unstopped_not_comparable(change):
    r=row(success=False);r.update(change)
    assert not summarize([r],['a'])['comparison_eligible']


def test_protected_failure_valid_but_not_success():
    r=row(success=False);r['outcome']='CONTACT_GUARD';r['guard_reasons']=['FORCE_LIMIT'];r['contact_guard']=True
    s=summarize([r],['a'])
    assert s['guarded_attempts']==1 and s['comparison_eligible'] and s['successes']==0


@pytest.mark.parametrize('change',[
    {'simulation_valid':False},{'physical_stopped':False},{'guard_reasons':['FORCE_LIMIT']},
    {'task_end_time_s':26.01},{'task_end_time_s':-1.},{'physical_end_time_s':4.},
    {'peak_force_N':float('nan')},{'peak_force_N':-1.},{'strict_precision_success':'yes'},
    {'simulation_valid':'yes'}, {'outcome':'made-up'}, {'status':'made-up'},
])
def test_invalid_or_contradictory_records_rejected(change):
    r=row();r.update(change)
    with pytest.raises(ValueError):summarize([r],['a'])


def test_duplicate_case_cannot_replace_failure():
    with pytest.raises(ValueError):summarize([row(),row(success=False)],['a'])


def test_task_versions_cannot_mix():
    r=row('b');r['comparison_key']='old-v3'
    with pytest.raises(ValueError):summarize([row(),r],['a','b'])
    with pytest.raises(ValueError):compare([row()],[r],['a'])


def test_all_failed_candidate_cannot_win_by_early_stopping():
    assert not compare([row()],[row(success=False)],['a'])['pilot_signal']


def test_pilot_signal_requires_same_success_and_ten_percent_time_gain():
    r=row();r['task_end_time_s']=4.4
    result=compare([row()],[r],['a'])
    assert result['pilot_signal'] and result['time_reduction_fraction']==pytest.approx(.12)
    assert result['scope']=='development_signal_not_paper_evidence'
    r['peak_force_N']=.012
    assert not compare([row()],[r],['a'])['pilot_signal']


def test_pilot_signal_requires_positive_success_and_no_more_guards():
    r=row(success=False)
    assert not compare([r],[r],['a'])['pilot_signal']
    with pytest.raises(ValueError):summarize([],[])


@pytest.mark.parametrize('outcome',['INVALID_SIMULATION','STOP_NOT_QUALIFIED','CONTACT_GUARD','MOTION_VIOLATION'])
def test_review_failure_category_must_match_independent_facts(outcome):
    r=row(success=False);r['outcome']=outcome
    with pytest.raises(ValueError):summarize([r],['a'])


def test_review_falsely_valid_invalid_attempt_cannot_create_pilot_signal():
    first=row(success=False);first['outcome']='INVALID_SIMULATION'
    second=row('b');second['task_end_time_s']=1.
    with pytest.raises(ValueError):
        compare([row(success=False),row('b',False)],[first,second],['a','b'])


def test_review_guard_facts_and_priority():
    r=row(success=False);r.update(guard_reasons=['FORCE_LIMIT'],contact_guard=True)
    with pytest.raises(ValueError):summarize([r],['a'])
    r['outcome']='CONTACT_GUARD'
    assert summarize([r],['a'])['comparison_eligible']
    r.update(simulation_valid=False,outcome='INVALID_SIMULATION')
    result=summarize([r],['a'])
    assert not result['comparison_eligible'] and result['invalid_attempts']==1 and result['guarded_attempts']==1
    r['outcome']='CONTACT_GUARD'
    with pytest.raises(ValueError):summarize([r],['a'])


@pytest.mark.parametrize('path',[
    'tools/validation/run_b2_search.py','tools/validation/native313_matrix_audit.py',
    'tools/validation/run_contact_candidate_stop.py','tools/validation/run_contact_cases.py',
])
def test_review_common_fingerprint_binds_real_dependencies(path):
    from tools.evaluation.paper_comparison import build_common_contract
    root=Path(__file__).resolve().parents[2]
    cfg=json.loads((root/'deliverables/task_variants/layered_referee_20261004/configuration.json').read_text(encoding='utf-8'))
    args=dict(canonical_model_sha256='a'*64,evaluator_sha256='b'*64)
    before=build_common_contract(cfg,**args)
    assert path in before['frozen_common_source_sha256']
    cfg['input_sha256'][path]='f'*64
    assert comparison_key(build_common_contract(cfg,**args))!=comparison_key(before)


def test_review_evaluator_runtime_and_initial_pose_bound():
    from tools.evaluation.paper_comparison import build_common_contract
    root=Path(__file__).resolve().parents[2]
    cfg=json.loads((root/'deliverables/task_variants/layered_referee_20261004/configuration.json').read_text(encoding='utf-8'))
    args=dict(canonical_model_sha256='a'*64,evaluator_sha256='b'*64)
    first=build_common_contract(cfg,**args)
    assert first['initial_pose']==dict(start_origin_z_m=-.004,target_depth_m=.004,roll_rad=0.,pitch_rad=0.,yaw_rad=0.)
    assert comparison_key(first)!=comparison_key(build_common_contract(cfg,**(args|{'evaluator_sha256':'c'*64})))
    cfg['runtime_proof']['review_test_mutation']=True
    assert comparison_key(first)!=comparison_key(build_common_contract(cfg,**args))
