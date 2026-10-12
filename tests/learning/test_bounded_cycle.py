"""Nonphysical checks of immutable evaluation and honest comparison."""
import importlib
import pytest
from tools.learning.bounded_contact import RunLedger


def api():return importlib.import_module('tools.learning.bounded_cycle')


def test_success_improvement_requires_new_success_and_no_lost_success():
    before=[dict(case=k,success=s) for k,s in zip('abcd',(True,False,False,True))]
    worse=[dict(case=k,success=s) for k,s in zip('abcd',(False,True,True,True))]
    better=[dict(case=k,success=s) for k,s in zip('abcd',(True,True,False,True))]
    assert api().compare_success(before,worse)['improved_without_regression'] is False
    assert api().compare_success(before,better)['improved_without_regression'] is True


def test_restored_comparison_rejects_changed_action_even_if_success_same():
    a=dict(transitions=[dict(action=[0.,0.,0.,0.])],outcome=dict(task_outcome='FULL_SUCCESS'),
           stop_samples=[],events=[],stop_time=1.,audit_end_time_s=3.,guard_facts={})
    b=dict(a); b['transitions']=[dict(action=[.1,0.,0.,0.])]
    assert api().same_physical_result(a,a)
    assert not api().same_physical_result(a,b)


def test_stage_order_refuses_holdout_sac_without_completed_new_baseline(tmp_path):
    ledger=RunLedger(tmp_path/'run.json')
    with pytest.raises(RuntimeError):api().require_stage(ledger,'holdout_sac')
    with pytest.raises(RuntimeError):api().require_stage(ledger,'training')


def test_new_scope_gate_requires_contact_and_safe_stop_but_not_task_success():
    evidence=[dict(case=case['name'],contact_cycles=12,guard_clear=True,physical_stopped=True,
                   simulation_valid=True,success=False) for case in api().cases(True)]
    api().validate_holdout_evidence(evidence)
    evidence[2]['contact_cycles']=0
    with pytest.raises(ValueError,match='contact'):api().validate_holdout_evidence(evidence)


def test_new_scope_gate_rejects_missing_or_duplicated_cases():
    evidence=[dict(case=case['name'],contact_cycles=12,guard_clear=True,physical_stopped=True,
                   simulation_valid=True,success=True) for case in api().cases(True)]
    evidence[-1]=dict(evidence[0])
    with pytest.raises(ValueError):api().validate_holdout_evidence(evidence)
