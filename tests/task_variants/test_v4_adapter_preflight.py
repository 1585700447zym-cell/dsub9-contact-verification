import pytest

@pytest.fixture(scope='module',autouse=True)
def runtime():
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()

def entry(spec,outcome='FULL_SUCCESS',gate=True):
    return dict(id=spec['id'],status='finished',verification_passed=gate,
        outcome=dict(task_outcome=outcome,simulation_valid=True,physical_stopped=True))

def test_schedule_exact_and_zero_mismatch_closes_following_budget():
    from tools.validation.run_v4_adapter_preflight import case_specs,next_case
    specs=case_specs();assert len(specs)==9
    assert [s['method'] for s in specs]==['F50','F50','F50','S50']+['B1']*5
    assert next_case([entry(specs[0],gate=False)]) is None
    assert next_case([entry(s) for s in specs]) is None
    assert next_case([entry(specs[0])])==specs[1]

def test_b1_qualified_guard_is_retained_but_residual_guard_stops():
    from tools.validation.run_v4_adapter_preflight import case_specs,next_case
    specs=case_specs();entries=[entry(s) for s in specs[:4]]
    entries.append(entry(specs[4],'CONTACT_GUARD'))
    assert next_case(entries)==specs[5]
    assert next_case([entry(specs[0],'CONTACT_GUARD')]) is None
    entries[-1]['outcome']['physical_stopped']=False
    assert next_case(entries) is None

def test_claim_once_and_new_budget(tmp_path):
    from tools.validation.run_v4_adapter_preflight import claim_run
    ledger=claim_run(tmp_path/'run')
    assert (ledger['max_new_episodes'],ledger['prior_cumulative'],ledger['cumulative_limit'])==(9,130,139)
    with pytest.raises(FileExistsError):claim_run(tmp_path/'run')

def test_bad_preparation_closes_all_budget_without_constructing_environment(tmp_path):
    from tools.validation.run_v4_adapter_preflight import execute
    import json
    (tmp_path/'preparation_binding.json').write_text('{}')
    with pytest.raises(RuntimeError):execute(tmp_path)
    ledger=json.loads((tmp_path/'run/ledger.json').read_text(encoding='utf8'))
    assert ledger['unused_closed']==9 and ledger['episodes']==[] and ledger['status']=='input_changed'

def test_script_has_fixed_times_and_zero_mode():
    from tools.validation.run_v4_adapter_preflight import script_action
    from types import SimpleNamespace
    snapshot=SimpleNamespace(time_s=.022,controller_state=dict(phase='INSERT',phase_start=0))
    assert script_action(snapshot,'zero')==[0]*4
    assert script_action(snapshot,'pulse')==[.1,-.1,.1,-.1]
    snapshot.time_s=.122
    assert script_action(snapshot,'pulse')==[0]*4

def test_postflight_source_change_closes_remaining_budget(tmp_path,monkeypatch):
    from tools.validation import run_v4_adapter_preflight as runner
    ledger=runner.claim_run(tmp_path/'run');ledger['episodes'].append(entry(runner.case_specs()[0]))
    monkeypatch.setattr(runner,'verify_inputs',lambda folder:(_ for _ in ()).throw(RuntimeError('changed')))
    with pytest.raises(RuntimeError):runner.close_run(tmp_path,ledger)
    import json
    saved=json.loads((tmp_path/'run/ledger.json').read_text(encoding='utf8'))
    assert saved['unused_closed']==8 and saved['status']=='input_changed'

def test_review_error_outside_episode_try_still_closes_budget(tmp_path,monkeypatch):
    from tools.validation import run_v4_adapter_preflight as runner
    import json
    monkeypatch.setattr(runner,'verify_inputs',lambda folder:{})
    monkeypatch.setattr(runner,'next_case',lambda entries:(_ for _ in ()).throw(OSError('case read failed')))
    with pytest.raises(OSError):runner.execute(tmp_path)
    ledger=json.loads((tmp_path/'run/ledger.json').read_text(encoding='utf8'))
    assert ledger['status']=='error' and ledger['unused_closed']==9 and ledger['ended_at']

def test_review_existing_stop_does_not_claim_or_construct_model(tmp_path,monkeypatch):
    from tools.validation import run_v4_adapter_preflight as runner
    from tools.learning.guarded_environment import LearningEnvironment
    monkeypatch.setattr(runner,'verify_inputs',lambda folder:{})
    def forbidden(*a,**kw):raise AssertionError('Model construction after STOP')
    monkeypatch.setattr(LearningEnvironment,'__init__',forbidden)
    (tmp_path/'STOP').write_text('stop')
    ledger=runner.execute(tmp_path)
    assert ledger['episodes']==[] and ledger['unused_closed']==9 and ledger['stop_requested']

def test_review_actual_reference_is_checked_using_preaction_origin():
    from tools.validation.run_v4_adapter_preflight import actual_reference_radius
    from types import SimpleNamespace
    s=SimpleNamespace(controller_state=dict(phase='SEARCH',search_origin=[0,0,0]),residual_enabled=True)
    row=dict(phase='RUNNING',reference_qpos=[.000001,.00012,0,1,0,0,0])
    assert actual_reference_radius(s,row,[0,0,0])>.00012+1e-12
    row['phase']='STOPPING'
    assert actual_reference_radius(s,row,[0,0,0]) is None

def test_review_execution_hashes_include_all_runtime_foundations():
    from tools.validation.run_v4_adapter_preflight import input_hashes
    h=input_hashes()
    for p in ['deliverables/b2_search_recovery/matrix_v1_7cases/results_index.json',
              'deliverables/learning_chain/b2_repaired_cycle_v2_20260928/runtime.json',
              'deliverables/learning_chain/b2_repaired_cycle_v2_20260928/admission.json']:
        assert p in h

def test_review_verify_inputs_rechecks_frozen_common_sources(tmp_path,monkeypatch):
    from tools.validation import run_v4_adapter_preflight as runner
    import json
    frozen=tmp_path/'frozen.json';frozen.write_text('old')
    cfg=dict(input_sha256={},common=dict(frozen_common_source_sha256={str(frozen):runner.sha(frozen)}))
    (tmp_path/'configuration.json').write_text(json.dumps(cfg));(tmp_path/'model.xml').write_text('xml')
    binding={n:runner.sha(tmp_path/n) for n in ('configuration.json','model.xml')}
    (tmp_path/'preparation_binding.json').write_text(json.dumps(binding))
    monkeypatch.setattr(runner,'input_hashes',lambda:{})
    frozen.write_text('changed')
    with pytest.raises(RuntimeError):runner.verify_inputs(tmp_path)
