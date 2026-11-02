"""Production rate wiring and restore ordering; no network calls or Adam steps."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
import torch
from tools.learning.admission import short_training_config
from tools.learning import sac_update


class FakeOptimizer:
    def __init__(self, lr):
        self.param_groups = [dict(lr=lr, params=[0])]
        self.state = {}
    def state_dict(self):
        return deepcopy(dict(param_groups=self.param_groups, state=self.state))
    def load_state_dict(self, value):
        self.param_groups, self.state = deepcopy(value['param_groups']), deepcopy(value['state'])
    def zero_grad(self, **kw):
        pass


class FakePolicy:
    def __init__(self, observations, actions, schedule, **kw):
        self.actor = SimpleNamespace(optimizer=FakeOptimizer(schedule(1)))
        self.critic = SimpleNamespace(optimizer=FakeOptimizer(schedule(1)))
        self.weight = torch.tensor(2.)
    def state_dict(self):
        return {'weight': self.weight.clone()}
    def load_state_dict(self, state):
        self.weight.copy_(state['weight'])


def updater(monkeypatch, rate='absent'):
    monkeypatch.setattr(sac_update, 'SACPolicy', FakePolicy)
    cfg = short_training_config()
    if rate != 'absent':
        cfg['learning']['actor_learning_rate'] = rate
    # Rate wiring tested independently of the deliberately strict old admission.
    class ProtocolUpdater(sac_update.SACUpdater):
        config_validator = staticmethod(lambda config: None)
    return ProtocolUpdater(cfg)


@pytest.mark.parametrize('rate', ['absent', 3e-4, 3e-5])
def test_actor_override_leaves_critic_and_temperature_at_original_rate(monkeypatch, rate):
    u = updater(monkeypatch, rate)
    expected = 3e-4 if rate == 'absent' else rate
    assert u.policy.actor.optimizer.param_groups[0]['lr'] == expected
    assert u.policy.critic.optimizer.param_groups[0]['lr'] == 3e-4
    assert u.temperature_optimizer.param_groups[0]['lr'] == 3e-4
    assert u.counts == dict(critic=0, actor=0, temperature=0, target=0)


@pytest.mark.parametrize('rate', [0., -1., float('nan'), float('inf'), True, '3e-5', None])
def test_invalid_actor_rate_is_refused_before_initialization(monkeypatch, rate):
    with pytest.raises(ValueError, match='learning rate'):
        updater(monkeypatch, rate)


@pytest.mark.parametrize('role', ['actor', 'critic', 'temperature'])
def test_wrong_optimizer_rate_is_refused_before_policy_or_alpha_changes(monkeypatch, role):
    u = updater(monkeypatch, 3e-5)
    saved = u._snapshot()
    saved['policy']['weight'].fill_(99.)
    saved['alpha'].fill_(99.)
    saved[role]['param_groups'][0]['lr'] = 1e-4
    before = u._snapshot()
    with pytest.raises(ValueError, match='learning rate'):
        u._restore(saved)
    after = u._snapshot()
    assert torch.equal(before['policy']['weight'], after['policy']['weight'])
    assert torch.equal(before['alpha'], after['alpha'])
    for key in ('actor', 'critic', 'temperature', 'counts'):
        assert before[key] == after[key]


def test_original_actor_state_cannot_overwrite_candidate_rate(monkeypatch):
    a, b = updater(monkeypatch, 3e-4), updater(monkeypatch, 3e-5)
    with pytest.raises(ValueError, match='learning rate'):
        b._restore(a._snapshot())
    assert b.policy.actor.optimizer.param_groups[0]['lr'] == 3e-5


def test_candidate_snapshot_roundtrip_restores_matching_rates_and_state(monkeypatch):
    a = updater(monkeypatch, 3e-5)
    saved = a._snapshot()
    saved['policy']['weight'].fill_(7.)
    a._restore(saved)
    assert a.policy.weight.item() == 7.
    assert a.policy.actor.optimizer.param_groups[0]['lr'] == 3e-5
    assert a.policy.critic.optimizer.param_groups[0]['lr'] == 3e-4
    assert a.temperature_optimizer.param_groups[0]['lr'] == 3e-4


def test_legacy_admission_still_refuses_new_candidate_field(monkeypatch):
    monkeypatch.setattr(sac_update, 'SACPolicy', FakePolicy)
    cfg = short_training_config()
    cfg['learning']['actor_learning_rate'] = 3e-5
    with pytest.raises(ValueError, match='configuration'):
        sac_update.SACUpdater(cfg)


@pytest.mark.parametrize('bad', [0., float('nan'), None, 3e-4])
def test_bad_second_group_rate_is_rejected_before_any_restore(monkeypatch, bad):
    u = updater(monkeypatch, 3e-5)
    saved = u._snapshot()
    second = dict(lr=bad, params=[1])
    if bad is None: del second['lr']
    saved['actor']['param_groups'].append(second)
    saved['policy']['weight'].fill_(99.)
    with pytest.raises(ValueError, match='learning rate'):
        u._restore(saved)
    assert u.policy.weight.item() == 2.
    assert len(u.policy.actor.optimizer.param_groups) == 1
