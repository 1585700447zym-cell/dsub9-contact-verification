from copy import deepcopy
import importlib
import pytest
from tools.learning.admission import short_training_config


def api(): return importlib.import_module('tools.learning.b2_sac_admission')


def record():
    return dict(version='b2_sac_update_admission_v1', capability='bounded_sac_update_probe',
        collection_admitted=True, update_admitted=True, runnable_trainer=False,
        parent_sha256=api().PARENT_SHA256, config=short_training_config(),
        execution_contract=api().execution_contract(), runtime={'native': 'fixed'},
        source_sha256={'old': 'a'}, gates={k: True for k in api().GATES})


@pytest.mark.parametrize('change', [dict(update_admitted=1), dict(runnable_trainer=True),
    dict(parent_sha256='changed'), dict(execution_contract={}), dict(gates={}),
    dict(source_sha256={}), dict(runtime={'native': 'other'})])
def test_incomplete_or_wrong_scope_qualification_refuses_updates(change):
    r = record(); r.update(change)
    with pytest.raises(ValueError): api().validate_record(r, current_sources={'old': 'a'}, runtime={'native': 'fixed'})


def test_exact_probe_qualification_does_not_authorize_full_training():
    r = record()
    api().validate_record(r, current_sources={'old': 'a'}, runtime={'native': 'fixed'})
    assert r['runnable_trainer'] is False


def test_changed_frozen_learning_configuration_is_rejected():
    r = record(); r['config']['learning']['entropy_initial'] = .1
    with pytest.raises(ValueError): api().validate_record(r, current_sources={'old': 'a'}, runtime={'native': 'fixed'})


@pytest.mark.parametrize('change', [dict(attempts=[]), dict(updates=0), dict(seed=7)])
def test_probe_refuses_missing_attempts_or_changed_update_budget(change, runtime):
    module = importlib.import_module('tools.validation.verify_sac_update')
    p = module.verification_protocol()
    p.update(change)
    with pytest.raises(ValueError): module.validate_protocol(p)


def test_parent_delivery_manifest_is_pinned_not_just_self_consistent(monkeypatch, runtime):
    import json
    m = api()
    parent = json.loads((m.ROOT / m.PARENT).read_text(encoding='utf-8'))
    original = m.digest
    monkeypatch.setattr(m, 'b1_parent', lambda runtime: None)
    monkeypatch.setattr(m, 'digest', lambda p: 'changed' if str(p).endswith('manifest.json') else original(p))
    with pytest.raises(ValueError, match='manifest'): m._parent(parent['runtime'])
