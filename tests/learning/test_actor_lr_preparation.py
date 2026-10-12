"""Candidate preparation cannot start model/physical work or reuse old authority."""
from copy import deepcopy
import importlib
import pytest


def api():
    return importlib.import_module('tools.learning.actor_lr_preparation')


def test_branches_change_only_actor_rate_and_branch_identity():
    m = api()
    a, b = m.preparation_config('A'), m.preparation_config('B')
    assert a['learning']['actor_learning_rate'] == 3e-4
    assert b['learning']['actor_learning_rate'] == 3e-5
    assert a['learning']['learning_rate'] == b['learning']['learning_rate'] == 3e-4
    b['learning']['actor_learning_rate'] = a['learning']['actor_learning_rate']
    b['comparison']['branch'] = 'A'
    assert a == b


@pytest.mark.parametrize('branch', ['A', 'B'])
def test_preparation_has_no_execution_budget(branch):
    c = api().preparation_config(branch)
    assert c['execution']['preparation_only'] is True
    assert c['execution']['authorized_dynamic_starts'] == 0
    assert c['execution']['authorized_optimizer_calls'] == 0
    assert c['execution']['authorized_model_forwards'] == 0
    assert api().validate_preparation_config(c) is None


@pytest.mark.parametrize('damage', ['public_rate', 'actor_rate', 'authority', 'source', 'branch', 'extra'])
def test_tampered_candidate_config_is_rejected(damage):
    m = api()
    c = m.preparation_config('B')
    if damage == 'public_rate': c['learning']['learning_rate'] = 3e-5
    if damage == 'actor_rate': c['learning']['actor_learning_rate'] = 3e-4
    if damage == 'authority': c['execution']['authorized_dynamic_starts'] = 8
    if damage == 'source': c['comparison']['parent_config_sha256'] = '0'*64
    if damage == 'branch': c['comparison']['branch'] = 'C'
    if damage == 'extra': c['unregistered'] = True
    with pytest.raises(ValueError): m.validate_preparation_config(c)


def test_source_config_pin_change_is_rejected(tmp_path, monkeypatch):
    m = api()
    source = tmp_path/'config.json'
    source.write_text('{}', encoding='utf-8')
    monkeypatch.setattr(m, 'PARENT_CONFIG', source)
    with pytest.raises(ValueError, match='Parent config'):
        m.preparation_config('B')


@pytest.mark.parametrize('method', ['predict', 'targets', '_targets', 'update'])
def test_preparation_updater_blocks_all_model_computation(method):
    m = api()
    # Block applies even before a real policy could be constructed.
    u = object.__new__(m.PreparationUpdater)
    with pytest.raises(RuntimeError, match='preparation'):
        getattr(u, method)(None)


def test_preparation_admission_refuses_claimed_old_authorization():
    m = api()
    with pytest.raises(ValueError, match='execution'):
        m.PreparationAdmission().verify()


def test_preparation_updater_uses_actor_override_without_allowing_prediction(monkeypatch):
    from test_actor_learning_rate import FakePolicy
    from tools.learning import sac_update
    m = api()
    monkeypatch.setattr(sac_update, 'SACPolicy', FakePolicy)
    u = m.PreparationUpdater(m.preparation_config('B'))
    assert u.policy.actor.optimizer.param_groups[0]['lr'] == 3e-5
    assert u.policy.critic.optimizer.param_groups[0]['lr'] == 3e-4
    assert u.temperature_optimizer.param_groups[0]['lr'] == 3e-4
    with pytest.raises(RuntimeError): u.predict(None)


def test_checkpoint_binding_rejects_another_branch_and_parent():
    m = api()
    a, b = m.preparation_config('A'), m.preparation_config('B')
    binding = m.checkpoint_binding(a, 'a'*64)
    assert m.validate_checkpoint_binding(binding, a, 'a'*64) is None
    with pytest.raises(ValueError): m.validate_checkpoint_binding(binding, b, 'a'*64)
    with pytest.raises(ValueError): m.validate_checkpoint_binding(binding, a, 'b'*64)
    bad = deepcopy(binding); bad['config_sha256'] = '0'*64
    with pytest.raises(ValueError): m.validate_checkpoint_binding(bad, a, 'a'*64)


def test_binding_cannot_use_missing_or_non_hash_source_manifest():
    m = api()
    for pin in ('', None, 'not-a-sha', 'g'*64):
        with pytest.raises(ValueError): m.checkpoint_binding(m.preparation_config('B'), pin)
