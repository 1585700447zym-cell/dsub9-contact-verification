from copy import deepcopy
import torch
import pytest
import run_probe as r

COMMON={'cases':[{'id':'y_neg_150','x_um':0,'y_um':-150},{'id':'aligned','x_um':0,'y_um':0}]}

def test_fixed_matrix_is_case_major_and_cannot_use_holdouts():
    s=r.attempt_specs(COMMON)
    assert len(s)==8 and len({x['id'] for x in s})==8
    assert [(x['case']['id'],x['profile']) for x in s]==[
        ('aligned','B2'),('aligned','F50'),('aligned','F12.5'),('aligned','G50'),
        ('y_neg_150','B2'),('y_neg_150','F50'),('y_neg_150','F12.5'),('y_neg_150','G50')]

def test_unfinished_attempt_has_no_retry():
    specs=r.attempt_specs(COMMON)
    with pytest.raises(RuntimeError):r.next_spec({'status':'running','episodes':[{'id':specs[0]['id'],'status':'running'}]},specs)

def test_finished_failure_keeps_fixed_next_case():
    specs=r.attempt_specs(COMMON)
    assert r.next_spec({'status':'running','episodes':[{'id':specs[0]['id'],'status':'finished','outcome':'TASK_FAILURE'}]},specs)==specs[1]

def test_closed_execution_cannot_consume_more_budget():
    assert r.next_spec({'status':'error','episodes':[]},r.attempt_specs(COMMON)) is None

def test_out_of_order_attempt_rejected():
    specs=r.attempt_specs(COMMON)
    with pytest.raises(RuntimeError):r.next_spec({'status':'running','episodes':[{'id':specs[1]['id'],'status':'finished'}]},specs)

def test_fault_keeps_successful_and_attempted_network_calls():
    ledger={'episodes':[{'profile':'F50','policy_calls':7,'policy_call_attempts':8,'status':'error'},
                        {'profile':'B2','policy_calls':0,'policy_call_attempts':0,'status':'finished'}]}
    r.reconcile_calls(ledger)
    assert ledger['policy_calls']==7 and ledger['policy_call_attempts']==8
    r.reconcile_calls(ledger)
    assert ledger['policy_calls']==7

def test_zero_baseline_cannot_have_network_calls():
    with pytest.raises(ValueError):r.reconcile_calls({'episodes':[{'profile':'B2','policy_calls':1,'policy_call_attempts':1}]})

def test_hidden_rng_change_invalidates_frozen_evaluation():
    a={'counts':{'critic':2000},'actor':torch.tensor([1.,2.]),'rng':torch.tensor([3,4],dtype=torch.uint8)};b=deepcopy(a)
    assert r.verify_frozen_state(a,b) is True
    b['rng'][0]=8
    with pytest.raises(ValueError):r.verify_frozen_state(a,b)

def test_model_change_invalidates_frozen_evaluation():
    a={'counts':{'critic':2000},'actor':torch.tensor([1.,2.]),'rng':torch.tensor([3,4],dtype=torch.uint8)};b=deepcopy(a)
    assert r.verify_frozen_state(a,b) is True
    b['actor'][0]=8
    with pytest.raises(ValueError):r.verify_frozen_state(a,b)

@pytest.mark.parametrize('failure_at',['construct','reset'])
def test_initialization_fault_preserves_original_error_and_attempt(tmp_path,monkeypatch,failure_at):
    # Replace only physical setup boundaries: this test must never reset MuJoCo.
    from types import SimpleNamespace
    import gzip,json
    import tools.learning.guarded_environment as environment
    import tools.validation.run_v4_adapter_preflight as wiring
    import deployment_profile
    class BrokenEnvironment:
        def __init__(self,**kwargs):
            if failure_at=='construct':raise LookupError('original setup failure')
            self.physical_steps=0;self.data=SimpleNamespace(time=0.)
            self.events=[];self.stop_samples=[];self.guard_facts={}
    class BrokenSession:
        def __init__(self,**kwargs):pass
        def reset(self,*args,**kwargs):raise LookupError('original setup failure')
    monkeypatch.setattr(environment,'LearningEnvironment',BrokenEnvironment)
    monkeypatch.setattr(wiring,'make_session',lambda *args:SimpleNamespace(controller_factory=None,geometry_checker=None))
    monkeypatch.setattr(deployment_profile,'ProfileSession',BrokenSession)
    monkeypatch.setattr(r,'OUT',tmp_path);(tmp_path/'model.xml').write_text('<unused/>')
    (tmp_path/'run').mkdir()  # The one-time execute claim creates this before rollout.
    spec=r.attempt_specs(COMMON)[0];entry={'id':spec['id'],'profile':'B2','status':'running','policy_calls':0,'policy_call_attempts':0}
    ledger={'episodes':[entry]};c=SimpleNamespace(updater=r.ZeroUpdater())
    with pytest.raises(LookupError,match='original setup failure'):
        r.rollout({'common':{'guard_config':{'max_rotation_from_start_rad':.2,'initial_roll_pitch_limit_rad':.1},'finish_criteria':{}}},c,spec,entry,ledger)
    assert entry['status']=='error' and 'original setup failure' in entry['error']
    assert entry['policy_calls']==entry['policy_call_attempts']==0
    assert entry['control_cycles']==entry['physical_substeps']==0
    assert 'control_cycles' in entry['unknown_cost_fields']
    assert (tmp_path/'run/ledger.json').exists()
    partial=json.loads(gzip.decompress((tmp_path/'run'/(spec['id']+'.error.json.gz')).read_bytes()))
    assert partial['entry']['error']==entry['error'] and partial['transitions']==[]
