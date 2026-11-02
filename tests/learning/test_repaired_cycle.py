"""Budget and zero-state inheritance, no optimizer or physical execution."""
import importlib
from copy import deepcopy
import pytest


def api(): return importlib.import_module('tools.learning.repaired_cycle')


def test_new_baseline_required_before_initial_and_training(tmp_path):
    ledger=api().RepairedLedger(tmp_path/'ledger.json')
    with pytest.raises(RuntimeError): ledger.start('initial','one')
    for i in range(4):
        ledger.start('baseline',str(i)); ledger.finish({})
    with pytest.raises(RuntimeError): ledger.start('training','one')
    ledger.start('initial','one')
    assert api().accounting(ledger.state)['cumulative_dynamic_starts']==14


def test_36_starts_count_failures_and_refuse_37th(tmp_path):
    ledger=api().RepairedLedger(tmp_path/'ledger.json')
    for stage,cap in ledger.CAPS.items():
        for i in range(cap):
            ledger.start(stage,str(i));ledger.finish({})
    assert ledger.state['dynamic_starts']==36
    assert api().accounting(ledger.state)['cumulative_dynamic_starts']==45
    with pytest.raises(RuntimeError): ledger.start('baseline','extra')


def test_failed_run_cannot_continue_after_reopening(tmp_path):
    path=tmp_path/'ledger.json';ledger=api().RepairedLedger(path)
    ledger.start('baseline','0');ledger.fail('fault')
    with pytest.raises(RuntimeError):api().RepairedLedger(path).start('baseline','1')
    assert api().accounting(ledger.state)['cumulative_dynamic_starts']==10


def test_initial_state_allows_only_binding_change():
    before=dict(binding={'old':1},updater=dict(counts=dict(critic=0,actor=0,temperature=0,target=0),
        policy={'weight':[1,2]},rng=[3]),replay={'rows':[]},budget={'total':0,'completed':0},
        sampler_count=0,update_attempts=0,archives={},attempts=[],history=[],rng={'warmup':[4]})
    after=deepcopy(before);after['binding']={'new':2}
    api().compare_initial_states(before,after)
    after['updater']['policy']['weight'][0]=3
    with pytest.raises(ValueError):api().compare_initial_states(before,after)


def test_nonempty_initial_state_cannot_be_inherited():
    state=dict(binding={},updater=dict(counts=dict(critic=1)),budget={'total':0,'completed':0},
        sampler_count=0,update_attempts=0,archives={},attempts=[],history=[])
    with pytest.raises(ValueError):api().compare_initial_states(state,state)


def test_manifest_cannot_reauthorize_its_own_modified_payload(tmp_path):
    import hashlib,json
    path=tmp_path/'manifest.json'
    path.write_text(json.dumps({'file':'old digest'}))
    pin=hashlib.sha256(path.read_bytes()).hexdigest()
    assert api().pinned_manifest(path,pin)=={'file':'old digest'}
    path.write_text(json.dumps({'file':'new digest matching tampered payload'}))
    with pytest.raises(ValueError):api().pinned_manifest(path,pin)


@pytest.mark.parametrize('changed',['python','versions','torch_dll_sha256','lock_sha256','executable'])
def test_native_repair_cannot_requalify_changed_learning_dependencies(changed):
    parent=dict(native={'old':1},python='3.13.5',versions={'torch':'2.12.1+cpu'},
        torch_dll_sha256={'torch.dll':'old'},lock_sha256='old',executable='qualified')
    current=deepcopy(parent);current['native']={'repaired':1}
    api().require_learning_runtime_unchanged(parent,current)
    current[changed]='changed'
    with pytest.raises(ValueError):api().require_learning_runtime_unchanged(parent,current)


@pytest.mark.parametrize('actual',[[],['module::one'],['module::one','module::one']])
def test_empty_partial_or_duplicated_test_receipt_is_rejected(actual):
    with pytest.raises(ValueError):api().require_complete_tests(actual,['module::one','module::two'])


def test_exact_complete_test_receipt_is_accepted():
    api().require_complete_tests(['module::two','module::one'],['module::one','module::two'])
