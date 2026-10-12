import pytest


def entry(name,outcome='FULL_SUCCESS'):
    return dict(id=name,status='finished',outcome=dict(task_outcome=outcome,simulation_valid=True,physical_stopped=True))


def test_first_negative_y_must_succeed_before_remaining_regressions():
    from tools.validation.run_search_load_preflight import next_case,case_specs
    assert next_case([])['id']=='y_neg_150'
    assert next_case([entry('y_neg_150','TASK_FAILURE')]) is None
    assert next_case([entry('y_neg_150')])['id']=='y_pos_150'
    assert [s['id'] for s in case_specs()]==['y_neg_150','y_pos_150','x_pos_150','x_neg_150','aligned']


@pytest.mark.parametrize('category',['CONTACT_GUARD','MOTION_VIOLATION','INVALID_SIMULATION','STOP_NOT_QUALIFIED'])
def test_any_protection_stops_five_case_schedule(category):
    from tools.validation.run_search_load_preflight import next_case
    assert next_case([entry('y_neg_150'),entry('y_pos_150',category)]) is None


def test_errors_close_actual_five_case_budget_and_preserve_attempt(tmp_path):
    import json
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()
    from tools.validation.run_search_load_preflight import claim_run,record_error,next_case
    from tools.validation.run_contact_cases import ContactCase
    ledger=claim_run(tmp_path/'run');e=dict(id='y_neg_150',status='running');ledger['episodes'].append(e)
    assert ledger['prior_cumulative']==119 and ledger['cumulative_limit']==124
    record_error(tmp_path/'run',ledger,e,RuntimeError('test'),ContactCase.aligned(),[],None,None)
    saved=json.loads((tmp_path/'run/ledger.json').read_text())
    assert saved['unused_closed']==4
    with pytest.raises(RuntimeError):next_case(saved['episodes'])
    with pytest.raises(FileExistsError):claim_run(tmp_path/'run')
