import pytest


def entry(name,outcome='FULL_SUCCESS'):
    return dict(id=name,status='finished',outcome=dict(task_outcome=outcome,simulation_valid=True,physical_stopped=True))


def test_schedule_stops_on_failed_target_and_all_protections():
    from tools.validation.run_layered_referee_preflight import next_case,case_specs
    assert next_case([])['id']=='y_neg_150'
    assert next_case([entry('y_neg_150','TASK_FAILURE')]) is None
    assert next_case([entry('y_neg_150')])['id']=='y_pos_150'
    for reason in ['CONTACT_GUARD','MOTION_VIOLATION','INVALID_SIMULATION','STOP_NOT_QUALIFIED']:
        assert next_case([entry('y_neg_150'),entry('y_pos_150',reason)]) is None
    assert [e['id'] for e in case_specs()]==['y_neg_150','y_pos_150','x_pos_150','x_neg_150','aligned']
    assert next_case([entry(e['id']) for e in case_specs()]) is None


def test_new_budget_is_separate_and_claim_once(tmp_path):
    from tools.validation.run_layered_referee_preflight import claim_run
    ledger=claim_run(tmp_path/'run')
    assert ledger['prior_cumulative']==125 and ledger['cumulative_limit']==130 and ledger['max_new_episodes']==5
    with pytest.raises(FileExistsError):claim_run(tmp_path/'run')


def test_prepare_and_execute_use_same_explicit_new_session():
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()
    from tools.validation.run_layered_referee_preflight import make_session
    from tools.learning.layered_session import LayeredReferenceSession
    from tools.model.layered_task import referee_metadata
    from tools.control.reference_search import ReferenceSearchRecovery
    from tools.control.search_recovery import SearchConfig
    from tools.control.risk_search import RotationRiskConfig
    from tools.control.load_search import SearchLoadConfig
    from dataclasses import asdict
    config=dict(b2_config=asdict(SearchConfig(total_action_time_s=25.)),rotation_risk=asdict(RotationRiskConfig()),search_load=asdict(SearchLoadConfig()))
    # No dynamics or MuJoCo model construction; only session/controller wiring.
    from tools.learning.guarded_environment import LearningEnvironment
    from types import SimpleNamespace
    env=object.__new__(LearningEnvironment);env.config=SimpleNamespace(linear_speed=.0008,linear_acceleration=.004)
    config['drive_limits']=dict(linear_speed_m_s=.0008,linear_acceleration_m_s2=.004)
    config['geometry_referee']=referee_metadata()
    s=make_session(env,config)
    assert isinstance(s,LayeredReferenceSession)
    assert isinstance(s.controller_factory(),ReferenceSearchRecovery)
    assert s.controller_factory().drive_config.linear_speed_m_s==.0008


def test_wrong_drive_limits_rejected_before_session_construction():
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()
    from tools.validation.run_layered_referee_preflight import make_session
    from types import SimpleNamespace
    env=SimpleNamespace(config=SimpleNamespace(linear_speed=.001,linear_acceleration=.005))
    config=dict(drive_limits=dict(linear_speed_m_s=.0008,linear_acceleration_m_s2=.005))
    with pytest.raises(ValueError,match='Drive limits'):make_session(env,config)


@pytest.mark.parametrize('changed',['configuration.json','model.xml'])
def test_prepared_configuration_and_model_cannot_change_unnoticed(tmp_path,changed):
    import hashlib,json
    from tools.validation.run_layered_referee_preflight import verify_prepared_files
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
    from tools.validation.run_layered_referee_preflight import execute
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
    from tools.validation import run_layered_referee_preflight as runner
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



def test_default_session_changes_only_referee_and_not_controller():
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()
    from tools.validation import run_layered_referee_preflight as new
    from tools.validation import run_deadline25_preflight as old
    from tools.learning.guarded_environment import LearningEnvironment
    from tools.model.layered_task import layered_pin_fit
    from types import SimpleNamespace
    env=object.__new__(LearningEnvironment);env.config=SimpleNamespace(linear_speed=.001,linear_acceleration=.005)
    a=old.make_session(env);b=new.make_session(env)
    assert a.controller_factory().metadata()==b.controller_factory().metadata()
    assert a.finish_criteria==b.finish_criteria
    assert b.geometry_checker is layered_pin_fit and a.geometry_checker is not layered_pin_fit
    assert new.TASK_ID=='dsub9_clearance120_layered_25s_v4'


@pytest.mark.parametrize('mode',['missing','wrong_tolerance','old_version'])
def test_rejects_unbound_or_wrong_referee(mode):
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()
    from tools.validation.run_layered_referee_preflight import make_session
    from tools.model.layered_task import referee_metadata
    from types import SimpleNamespace
    config=dict(b2_config=dict(total_action_time_s=25.),drive_limits=dict(linear_speed_m_s=.001,linear_acceleration_m_s2=.005),geometry_referee=referee_metadata())
    if mode=='missing':del config['geometry_referee']
    elif mode=='wrong_tolerance':config['geometry_referee']['tolerance_m']=1e-6
    else:config['geometry_referee']['id']='old_whole_shaft'
    env=SimpleNamespace(config=SimpleNamespace(linear_speed=.001,linear_acceleration=.005))
    with pytest.raises(ValueError,match='Geometry referee'):make_session(env,config)
