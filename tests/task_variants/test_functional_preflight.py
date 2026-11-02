import pytest


def entry(name, outcome='FULL_SUCCESS'):
    return dict(id=name,status='finished',outcome=dict(task_outcome=outcome,simulation_valid=True,physical_stopped=True))


def test_known_failure_is_first_and_unfixed_failure_closes_remaining_budget():
    from tools.validation.run_functional_preflight import next_case,case_specs
    assert next_case([])['id']=='y_pos_150'
    assert next_case([entry('y_pos_150','TASK_FAILURE')]) is None
    assert next_case([entry('y_pos_150')])['id']=='y_neg_150'
    assert next_case([entry('y_pos_150'),entry('y_neg_150','TASK_FAILURE')])['id']=='x_pos_150'
    assert len(case_specs())==9


@pytest.mark.parametrize('outcome',['MOTION_VIOLATION','CONTACT_GUARD','INVALID_SIMULATION','STOP_NOT_QUALIFIED'])
def test_any_protection_stops_new_runs(outcome):
    from tools.validation.run_functional_preflight import next_case
    assert next_case([entry('y_pos_150'),entry('y_neg_150',outcome)]) is None


def test_unfinished_attempt_and_wrong_order_cannot_restart():
    from tools.validation.run_functional_preflight import next_case
    with pytest.raises(RuntimeError):next_case([dict(id='y_pos_150',status='running')])
    with pytest.raises(RuntimeError):next_case([entry('aligned')])


def test_claim_new_budget_cannot_reuse_an_existing_run(tmp_path):
    from tools.validation.run_functional_preflight import claim_run
    ledger=claim_run(tmp_path/'run')
    assert ledger['prior_cumulative']==117 and ledger['cumulative_limit']==126
    before=(tmp_path/'run/ledger.json').read_bytes()
    with pytest.raises(FileExistsError):claim_run(tmp_path/'run')
    assert (tmp_path/'run/ledger.json').read_bytes()==before


@pytest.mark.parametrize('archive_fails',[False,True])
def test_error_before_first_checkpoint_preserves_live_controller_events(tmp_path,monkeypatch,archive_fails):
    import gzip,json
    from types import SimpleNamespace
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()
    from tools.validation.run_functional_preflight import claim_run,record_error
    from tools.validation import run_clearance_preflight as helper
    from tools.validation.run_contact_cases import ContactCase
    ledger=claim_run(tmp_path/'run');attempt=dict(id='y_pos_150',status='running')
    ledger['episodes'].append(attempt)
    events=[dict(time_s=.1,phase='UNLOAD',reason='LOADED_ROTATION_RISK',relative_rotation_rad=.027,axial_force_N=-.02)]
    session=SimpleNamespace(cycle_id=51,controller=SimpleNamespace(events=events))
    if archive_fails:
        monkeypatch.setattr(helper,'archive_episode',lambda *a:(_ for _ in ()).throw(OSError('disk failure')))
    record_error(tmp_path/'run',ledger,attempt,RuntimeError('archive boundary'),ContactCase.aligned(),[],None,session)
    if not archive_fails:
        saved=json.loads(gzip.decompress((tmp_path/'run/y_pos_150.error.json.gz').read_bytes()))
        assert saved['controller_events']==events
    receipt=json.loads((tmp_path/'run/ledger.json').read_text())
    assert receipt['episodes'][0]['error_facts']['controller_events']==events
