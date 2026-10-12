import pytest


def entry(name,outcome='FULL_SUCCESS'):
    return dict(id=name,status='finished',outcome=dict(task_outcome=outcome,simulation_valid=True,physical_stopped=True))


def test_schedule_stops_on_failed_target_and_all_protections():
    from tools.validation.run_compliant_search_preflight import next_case,case_specs
    assert next_case([])['id']=='y_neg_150'
    assert next_case([entry('y_neg_150','TASK_FAILURE')]) is None
    assert next_case([entry('y_neg_150')])['id']=='y_pos_150'
    for reason in ['CONTACT_GUARD','MOTION_VIOLATION','INVALID_SIMULATION','STOP_NOT_QUALIFIED']:
        assert next_case([entry('y_neg_150'),entry('y_pos_150',reason)]) is None
    assert [e['id'] for e in case_specs()]==['y_neg_150','y_pos_150','x_pos_150','x_neg_150','aligned']
    assert next_case([entry(e['id']) for e in case_specs()]) is None


def test_new_budget_is_separate_and_claim_once(tmp_path):
    from tools.validation.run_compliant_search_preflight import claim_run
    ledger=claim_run(tmp_path/'run')
    assert ledger['prior_cumulative']==121 and ledger['cumulative_limit']==126 and ledger['max_new_episodes']==5
    with pytest.raises(FileExistsError):claim_run(tmp_path/'run')


def test_prepare_and_execute_use_same_explicit_new_session():
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()
    from tools.validation.run_compliant_search_preflight import make_session
    from tools.learning.compliant_session import CompliantSearchSession
    from tools.control.compliant_search import CompliantSearchRecovery
    from tools.control.search_recovery import SearchConfig
    from tools.control.risk_search import RotationRiskConfig
    from tools.control.load_search import SearchLoadConfig
    from dataclasses import asdict
    config=dict(b2_config=asdict(SearchConfig()),rotation_risk=asdict(RotationRiskConfig()),search_load=asdict(SearchLoadConfig()))
    # No dynamics or MuJoCo model construction; only session/controller wiring.
    from tools.learning.guarded_environment import LearningEnvironment
    s=make_session(object.__new__(LearningEnvironment),config)
    assert isinstance(s,CompliantSearchSession)
    assert isinstance(s.controller_factory(),CompliantSearchRecovery)


@pytest.mark.parametrize('changed',['configuration.json','model.xml'])
def test_prepared_configuration_and_model_cannot_change_unnoticed(tmp_path,changed):
    import hashlib,json
    from tools.validation.run_compliant_search_preflight import verify_prepared_files
    for name in ['configuration.json','model.xml']:(tmp_path/name).write_text('original',encoding='utf-8')
    binding={n:hashlib.sha256((tmp_path/n).read_bytes()).hexdigest() for n in ['configuration.json','model.xml']}
    (tmp_path/'preparation_binding.json').write_text(json.dumps(binding),encoding='utf-8')
    verify_prepared_files(tmp_path)
    (tmp_path/changed).write_text('changed',encoding='utf-8')
    with pytest.raises(RuntimeError,match='Prepared file changed'):verify_prepared_files(tmp_path)


def test_changed_preparation_closes_unused_budget_before_any_episode(tmp_path):
    import json,hashlib
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()
    from tools.validation.run_compliant_search_preflight import execute
    (tmp_path/'configuration.json').write_text('{"input_sha256":{}}',encoding='utf-8')
    (tmp_path/'model.xml').write_text('original',encoding='utf-8')
    binding={n:hashlib.sha256((tmp_path/n).read_bytes()).hexdigest() for n in ['configuration.json','model.xml']}
    (tmp_path/'preparation_binding.json').write_text(json.dumps(binding),encoding='utf-8')
    (tmp_path/'model.xml').write_text('changed',encoding='utf-8')
    with pytest.raises(RuntimeError,match='Prepared file changed'):execute(tmp_path)
    ledger=json.loads((tmp_path/'run/ledger.json').read_text(encoding='utf-8'))
    assert ledger['status']=='input_changed' and ledger['unused_closed']==5 and ledger['episodes']==[]


@pytest.mark.parametrize('failure',['model_changed','model_missing','source_changed'])
def test_postflight_input_failure_closes_budget_and_retains_completed_episode(tmp_path,monkeypatch,failure):
    import json,hashlib
    from tools.validation import run_compliant_search_preflight as runner
    ledger=runner.claim_run(tmp_path/'run');ledger['episodes'].append(entry('y_neg_150'))
    for name in ['configuration.json','model.xml']:(tmp_path/name).write_text('original',encoding='utf-8')
    binding={n:hashlib.sha256((tmp_path/n).read_bytes()).hexdigest() for n in ['configuration.json','model.xml']}
    (tmp_path/'preparation_binding.json').write_text(json.dumps(binding),encoding='utf-8')
    config={'input_sha256':{'source':'original'}}
    monkeypatch.setattr(runner,'input_hashes',lambda:{'source':'original'})
    if failure=='model_changed':(tmp_path/'model.xml').write_text('changed',encoding='utf-8')
    if failure=='model_missing':(tmp_path/'model.xml').unlink()
    if failure=='source_changed':monkeypatch.setattr(runner,'input_hashes',lambda:{'source':'changed'})
    with pytest.raises((OSError,RuntimeError)):runner.close_run(tmp_path,ledger,config)
    saved=json.loads((tmp_path/'run/ledger.json').read_text(encoding='utf-8'))
    assert saved['status']=='input_changed' and saved['unused_closed']==4
    assert saved['episodes']==[entry('y_neg_150')]
    assert saved['inputs_unchanged'] is False and saved['ended_at'] and saved['error']
