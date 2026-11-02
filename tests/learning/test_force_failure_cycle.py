"""New execution gate and durable budget checks, no physical calls."""
from copy import deepcopy
import importlib,importlib.util,json
import pytest

def api():
    assert importlib.util.find_spec('tools.learning.force_failure_cycle') is not None,'New execution gate is absent'
    return importlib.import_module('tools.learning.force_failure_cycle')

def test_config_preserves_learning_and_guard_parameters():
    from tools.learning.force_failure_preparation import force_config
    m=api();old=force_config();new=m.cycle_config()
    for k in old.keys()-{'version','execution'}:assert new[k]==old[k]
    assert new['execution']['force_failure_stop']==dict(consecutive=2,total=3)
    assert new['execution']['episode_rules']=='force_only_v1'
    bad=deepcopy(new);bad['action']['scale'][2]=.005
    with pytest.raises(ValueError):m.validate_config(bad)

def test_stage_order_and_32_new_starts_include_all_evaluations(tmp_path):
    m=api();ledger=m.ForceLedger(tmp_path/'ledger.json')
    with pytest.raises(RuntimeError):ledger.start('training','train_00')
    for stage,n in ledger.CAPS.items():
        for i in range(n):ledger.start(stage,str(i));ledger.finish(dict(synthetic_only=True))
    result=m.accounting(ledger.state)
    assert result['new_dynamic_starts']==32 and result['cumulative_dynamic_starts']==68
    with pytest.raises(RuntimeError):ledger.start('initial','extra')

@pytest.mark.parametrize('change',('starts','updates','lineage','frequency','retry','synthetic'))
def test_budget_rejects_unapproved_expansion(change):
    m=api();b=m.proposed_budget()
    if change=='starts':b['new_dynamic_cap']=33
    elif change=='updates':b['formal_optimizer_batches']=4501
    elif change=='lineage':b['previous_dynamic_starts']=35
    elif change=='frequency':b['force_failure_stop']['total']=4
    elif change=='retry':b['automatic_retry']=True
    else:b['new_synthetic_updates']=1
    with pytest.raises(ValueError):m.validate_budget(b)

def test_authorization_requires_exact_candidate_and_complete_budget():
    m=api();pin='a'*64
    r=dict(version='force_cycle_user_authorization_v1',approved=True,candidate_sha256=pin,
        budget=m.proposed_budget(),user_confirmation='synthetic test authorization only')
    m.validate_authorization(r,pin)
    for key,value in [('approved',False),('candidate_sha256','b'*64),('user_confirmation','')]:
        bad=deepcopy(r);bad[key]=value
        with pytest.raises(ValueError):m.validate_authorization(bad,pin)
    with pytest.raises(ValueError):m.validate_authorization(None,pin)

def test_missing_authorization_refuses_before_candidate_or_runtime(tmp_path,monkeypatch):
    m=api();monkeypatch.setattr(m,'DELIVERY',tmp_path)
    def forbidden(*a,**kw):raise AssertionError('Candidate/runtime must not run without authorization')
    monkeypatch.setattr(m,'verify_candidate',forbidden)
    with pytest.raises(ValueError,match='authorization'):
        m.ForceAdmission(tmp_path/'candidate.json',expected_digest='a'*64,authorization_digest=None)
    assert not (tmp_path/'run').exists()

def test_parent_manifest_allows_additions_but_rejects_changed_existing_bytes(tmp_path):
    m=api();(tmp_path/'old.py').write_text('original')
    manifest={'old.py':m.digest(tmp_path/'old.py')}
    (tmp_path/'new.py').write_text('new')
    m.verify_parent_files(tmp_path,manifest)
    (tmp_path/'old.py').write_text('changed')
    with pytest.raises((RuntimeError,ValueError)):m.verify_parent_files(tmp_path,manifest)

def test_controlled_stop_remains_closed_after_reopening(tmp_path):
    from tools.learning.bounded_contact import ForceFailureStop
    m=api();p=tmp_path/'ledger.json';ledger=m.ForceLedger(p)
    for i in range(4):ledger.start('initial',str(i));ledger.finish({})
    ledger.start('training','train_00');ledger.finish(dict(task_outcome='CONTACT_GUARD'))
    ledger.start('training','train_01');ledger.finish(dict(task_outcome='CONTACT_GUARD'))
    ledger.stop(ForceFailureStop('two_consecutive_force_failures','train_01'))
    with pytest.raises(RuntimeError):m.ForceLedger(p).start('training','train_02')
    state=json.loads(p.read_text());assert state['active'] is None and state['dynamic_starts']==6

def test_initial_state_comparison_allows_only_binding_and_registered_version():
    m=api()
    old=dict(version='bounded_checkpoint_v2',binding={'old':True},updater=dict(counts={'critic':0},weights=[1]),
        budget=dict(total=0,completed=0),sampler_count=0,update_attempts=0,archives={},attempts=[],history=[],rng={'a':[1,2]})
    new=deepcopy(old);new.update(version='force_only_checkpoint_v1',binding={'new':True})
    m.compare_initial_states(old,new)
    new['rng']['a'][0]=9
    with pytest.raises(ValueError):m.compare_initial_states(old,new)
