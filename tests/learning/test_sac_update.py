"""Actual SAC optimizers and an independent target/permission oracle."""
from copy import deepcopy
from dataclasses import replace
import importlib
import math

import pytest
import torch

from tools.learning.admission import short_training_config
from tools.learning.audited_replay import ReplayBatch


def api(): return importlib.import_module('tools.learning.sac_update')


def batch(active=True):
    g = torch.Generator().manual_seed(711)
    n = 16
    return ReplayBatch(observations=torch.randn(n, 120, generator=g) * .1,
        next_observations=torch.randn(n, 120, generator=g) * .1,
        actions=torch.zeros(n, 4), rewards=torch.full((n, 1), -.1),
        discounts=torch.full((n, 1), math.exp(-.002 / 10)), dt=torch.full((n, 1), .002),
        terminated=torch.zeros(n, 1, dtype=torch.bool), truncated=torch.zeros(n, 1, dtype=torch.bool),
        action_active=torch.full((n, 1), active), next_action_active=torch.full((n, 1), active))


def equal(a, b):
    if isinstance(a, torch.Tensor): assert torch.equal(a, b)
    elif isinstance(a, dict):
        assert a.keys() == b.keys()
        for k in a: equal(a[k], b[k])
    elif isinstance(a, (list, tuple)):
        assert len(a) == len(b)
        for x, y in zip(a, b): equal(x, y)
    else: assert a == b


def state(u):
    return deepcopy(dict(policy=u.policy.state_dict(), actor=u.policy.actor.optimizer.state_dict(),
        critic=u.policy.critic.optimizer.state_dict(), alpha=u.log_alpha,
        temperature=u.temperature_optimizer.state_dict(), counts=u.counts, rng=u.rng_state))


def test_real_update_changes_both_critics_actor_temperature_and_soft_target():
    u = api().SACUpdater(short_training_config())
    before = u.fingerprints()
    target = [p.detach().clone() for p in u.policy.critic_target.parameters()]
    stats = u.update(batch())
    after = u.fingerprints()
    assert all(before[k] != after[k] for k in ('actor', 'critic', 'target', 'alpha'))
    assert u.counts == dict(critic=1, actor=1, temperature=1, target=1)
    assert stats['active_rows'] == 16 and stats['alpha_before'] == pytest.approx(.01)
    assert all(math.isfinite(x) for x in stats.values() if isinstance(x, float))
    for old, q, target in zip(target, u.policy.critic.parameters(), u.policy.critic_target.parameters()):
        torch.testing.assert_close(target, .995 * old + .005 * q.detach(), rtol=1e-6, atol=1e-7)
    for network in u.policy.critic.q_networks:
        assert any(u.policy.critic.optimizer.state[p]['step'] == 1 for p in network.parameters())


def test_inactive_batch_preserves_actor_temperature_and_adam_momentum():
    u = api().SACUpdater(short_training_config())
    u.update(batch())
    before = state(u)
    stats = u.update(batch(False))
    equal(before['actor'], u.policy.actor.optimizer.state_dict())
    equal(before['temperature'], u.temperature_optimizer.state_dict())
    equal(before['alpha'], u.log_alpha)
    for k, v in u.policy.actor.state_dict().items(): equal(before['policy']['actor.' + k], v)
    assert u.counts == dict(critic=2, actor=1, temperature=1, target=2)
    assert stats['actor_loss'] is None and stats['temperature_loss'] is None


def test_target_oracle_zero_action_no_entropy_terminal_and_truncated(monkeypatch):
    u = api().SACUpdater(short_training_config())
    b = batch(False)
    b.terminated[0] = True
    b.truncated[1] = True
    b.dt[1] = .001
    b.discounts[1] = math.exp(-.001 / 10)
    actions = []
    def q_next(obs, a):
        actions.append(a.clone())
        return torch.full((len(a), 1), 3.), torch.full((len(a), 1), 5.)
    monkeypatch.setattr(u.policy.critic_target, 'forward', q_next)
    target = u.targets(b)
    assert torch.count_nonzero(actions[0]) == 0
    assert target[0].item() == pytest.approx(-.1)
    torch.testing.assert_close(target[1:], b.rewards[1:] + b.discounts[1:] * 3.)
    assert not target.requires_grad


def test_actor_receives_q_action_gradient_not_only_entropy(monkeypatch):
    u = api().SACUpdater(short_training_config())
    with torch.no_grad(): u.log_alpha.fill_(-100)
    def q(obs, a):
        value = a.sum(1, keepdim=True) + sum(p.sum() * 0 for p in u.policy.critic.parameters())
        return value, value
    monkeypatch.setattr(u.policy.critic, 'forward', q)
    before = u.fingerprints()['actor']
    u.update(batch())
    assert sum(p.grad.abs().sum().item() for p in u.policy.actor.parameters() if p.grad is not None) > .001
    assert before != u.fingerprints()['actor']
    assert all(p.requires_grad for p in u.policy.critic.parameters())
    assert all(p.grad is None for p in u.policy.critic_target.parameters())


def test_late_optimizer_failure_rolls_back_entire_batch_and_latches(monkeypatch):
    u = api().SACUpdater(short_training_config())
    u.update(batch())  # Adam moments exist before the fault.
    before = state(u)
    monkeypatch.setattr(u.policy.actor.optimizer, 'step', lambda: (_ for _ in ()).throw(RuntimeError('diskless fault')))
    with pytest.raises(RuntimeError): u.update(batch())
    equal(before, state(u))
    assert u.failed
    with pytest.raises(RuntimeError, match='failed'): u.update(batch())


@pytest.mark.parametrize('field,value', [
    ('rewards', float('nan')), ('actions', 1.1), ('discounts', .99), ('dt', 0.)])
def test_bad_batch_cannot_change_networks_or_optimizer_state(field, value):
    u = api().SACUpdater(short_training_config())
    b = batch()
    getattr(b, field)[0] = value
    before = state(u)
    with pytest.raises(ValueError): u.update(b)
    equal(before, state(u))


def test_nonfinite_actor_gradient_rolls_back_already_updated_critic():
    u = api().SACUpdater(short_training_config())
    before = state(u)
    handle = next(u.policy.actor.parameters()).register_hook(lambda g: torch.full_like(g, float('nan')))
    with pytest.raises(ValueError): u.update(batch())
    handle.remove()
    equal(before, state(u))


def test_private_random_state_is_reproducible_without_changing_global_rng():
    global_rng = torch.get_rng_state().clone()
    a, b = api().SACUpdater(short_training_config()), api().SACUpdater(short_training_config())
    assert torch.equal(global_rng, torch.get_rng_state())
    a.update(batch())
    torch.rand(10)
    b.update(batch())
    assert a.fingerprints() == b.fingerprints()
    assert torch.equal(a.rng_state, b.rng_state)


def test_permission_flags_are_strict_not_broadcast_or_numeric():
    u = api().SACUpdater(short_training_config())
    with pytest.raises(ValueError): u.update(replace(batch(), action_active=torch.ones(16, 1)))
    assert u.counts['critic'] == 0


def test_inactive_rows_do_not_dilute_actor_or_temperature_loss():
    # The active minibatch is identical; critic is held constant to isolate the actor objective.
    a, b = api().SACUpdater(short_training_config()), api().SACUpdater(short_training_config())
    x = batch()
    mixed = replace(x, action_active=x.action_active.clone())
    mixed.action_active[8:] = False
    for u in (a, b):
        def q(obs, actions, u=u):
            value = actions.sum(1, keepdim=True) + sum(p.sum() * 0 for p in u.policy.critic.parameters())
            return value, value
        u.policy.critic.forward = q
    # Match target sampling draws so only the actor's active-row selection is compared.
    a._targets = b._targets = lambda data: data.rewards
    a.update(mixed)
    first_half = ReplayBatch(**{k: getattr(x, k)[:8] for k in ReplayBatch.__dataclass_fields__})
    b.update(first_half)
    assert a.fingerprints()['actor'] == b.fingerprints()['actor']
    assert a.fingerprints()['alpha'] == b.fingerprints()['alpha']
