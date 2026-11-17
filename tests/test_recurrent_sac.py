"""Exercise sequence math with generated tensors, without advancing the simulator."""
from copy import deepcopy
from dataclasses import replace
import math

import numpy as np
import pytest
import torch

from tools.learning.five_axis_contract import learning_config
from tools.learning.recurrent_sac import RecurrentActor, RecurrentUpdater


def updater():
    return RecurrentUpdater(learning_config()['learning'])


def batch(active=True):
    from tests.learning.test_five_axis_learning import obs
    from tools.learning.recurrent_replay import SequenceReplayBatch

    # One burn-in transition; suffix spans active, inactive and terminal rows.
    enabled = [False, active, False, active, False]
    observations = torch.tensor(np.stack([obs(v) for v in enabled]), dtype=torch.float32)[None]
    observations[0, :, 24] = torch.arange(5) * .1
    flag = torch.tensor(enabled)[None, :, None]
    valid = torch.ones((1, 4, 1), dtype=torch.bool)
    terminal = torch.zeros_like(valid)
    terminal[:, -1] = True
    learn = valid.clone()
    learn[:, 0] = False
    dt = torch.full((1, 4, 1), .002)
    return SequenceReplayBatch(observations=observations, observation_valid_mask=torch.ones_like(flag),
        actions=torch.zeros(1, 4, 5), rewards=torch.arange(4, dtype=torch.float32)[None, :, None],
        dt=dt, discounts=torch.exp(-dt/10), terminated=terminal, truncated=torch.zeros_like(valid),
        action_active=flag[:, :-1], next_action_active=flag[:, 1:], valid_mask=valid, learn_mask=learn,
        episode_ids=('synthetic',), start_cycles=(1,), prefix_lengths=(1,), burn_in=1)


def test_online_sequence_parity_padding_and_causality():
    actor = RecurrentActor()
    observations = torch.randn(2, 9, 140)
    valid = torch.ones(2, 9, 1, dtype=torch.bool)
    valid[0, :2] = False
    valid[1, -3:] = False
    mu, log_std, final = actor.forward_sequence(observations, None, valid)
    for b in range(2):
        h = None
        for t in valid[b, :, 0].nonzero().flatten():
            m, ls, h = actor.step(observations[b:b+1, t], h)
            torch.testing.assert_close(m[0], mu[b, t])
            torch.testing.assert_close(ls[0], log_std[b, t])
        torch.testing.assert_close(h[:, 0], final[:, b])
    altered = observations.clone()
    altered[:, 6:] += 7.
    altered[~valid.expand_as(altered)] = 900.
    mu2, _, _ = actor.forward_sequence(altered, None, valid)
    torch.testing.assert_close(mu[:, :6], mu2[:, :6])


def test_burn_in_detaches_prefix_and_critics_are_independent():
    u = updater()
    x = torch.randn(1, 8, 140, requires_grad=True)
    mask = torch.ones(1, 8, 1, dtype=torch.bool)
    u.actor.encode_suffix(x, mask, 3).sum().backward()
    assert not x.grad[:, :3].any() and x.grad[:, 3:].abs().sum() > 0
    modules = [u.actor, *u.critics, *u.target_critics]
    assert len({m.gru.weight_hh_l0.data_ptr() for m in modules}) == 5


def test_targets_use_actual_next_history_zero_inactive_and_terminal(monkeypatch):
    u = updater()
    data = batch(False)
    data.validate()
    captured = []
    for i, q in enumerate(u.target_critics):
        def sentinel(encoded, actions, i=i):
            captured.append(actions.detach().clone())
            return encoded[:, :1] + i * 10
        monkeypatch.setattr(q, 'q', sentinel)
    with torch.no_grad():
        expected_codes = [q.encode_sequence(data.observations, None, data.observation_valid_mask)[0]
                          for q in u.target_critics]
        expected = torch.minimum(expected_codes[0][0, 2:, :1], expected_codes[1][0, 2:, :1] + 10)
        target = u.targets(data)
        torch.testing.assert_close(target[:-1], data.rewards[0, 1:-1] + math.exp(-.002/10) * expected[:-1])
        torch.testing.assert_close(target[-1], data.rewards[0, -1])
    assert len(captured) == 2 and all(not a.any() for a in captured)


def test_update_resume_inactive_mask_and_rollback(monkeypatch):
    from tools.learning.sac_checkpoint import _same
    u = updater()
    active = batch()
    stats = u.update(active)
    assert stats['active_rows'] == 2 and stats['batch_rows'] == 3
    assert stats['actor_grad_norm'] > 0
    before = u.state_dict()
    u.update(batch(False))
    after = u.state_dict()
    for key in ('actor', 'actor_optimizer', 'temperature_optimizer', 'log_alpha'):
        assert _same(before[key], after[key])
    assert u.counts == dict(critic=2, target=2, actor=1, temperature=1)
    clone = updater()
    clone.load_state_dict(after)
    assert u.update(active) == clone.update(active)
    assert _same(u.state_dict(), clone.state_dict())
    saved = u.state_dict()
    def damage(*args, **kwargs):
        with torch.no_grad():
            next(u.actor.parameters()).fill_(float('nan'))
        raise RuntimeError('injected late failure')
    monkeypatch.setattr(u.actor_optimizer, 'step', damage)
    with pytest.raises(RuntimeError, match='injected'):
        u.update(active)
    assert u.failed and _same(saved, u._snapshot())
    with pytest.raises(RuntimeError):
        u.update(active)


def test_policy_update_reencodes_behavior_with_updated_critics(monkeypatch):
    u = updater()
    encoded_weights = []
    critic = u.critics[0]
    original = critic.encode_suffix
    def capture(*args):
        encoded_weights.append(critic.gru.weight_ih_l0.detach().clone())
        return original(*args)
    monkeypatch.setattr(critic, 'encode_suffix', capture)
    result = u.update(batch())
    assert len(encoded_weights) == 2 and not torch.equal(*encoded_weights)
    torch.testing.assert_close(encoded_weights[1], critic.gru.weight_ih_l0)
    assert result['actor_grad_norm'] > 0


def test_extra_padding_does_not_affect_learning_or_target_sampling():
    source = batch()
    padded_fields = {}
    for key, value in vars(source).items():
        if isinstance(value, torch.Tensor):
            extra = torch.zeros_like(value[:, :1])
            if value.is_floating_point():
                extra.fill_(17.)
            padded_fields[key] = torch.cat((value, extra), dim=1)
    padded = replace(source, **padded_fields)
    first, second = updater(), updater()
    a, b = first.update(source), second.update(padded)
    assert a == pytest.approx(b)
    assert torch.equal(first.generator.get_state(), second.generator.get_state())
    for name in ('actor', 'critics', 'target_critics'):
        for p, q in zip(getattr(first, name).parameters(), getattr(second, name).parameters()):
            torch.testing.assert_close(p, q)


def test_malformed_checkpoint_rejected_without_mutation():
    from tools.learning.sac_checkpoint import _same
    u = updater()
    u.update(batch())
    good = u.state_dict()
    bad = deepcopy(good)
    bad['critic_optimizer']['state'][0]['exp_avg_sq'].fill_(-1)
    with pytest.raises(ValueError):
        u.load_state_dict(bad)
    assert _same(good, u.state_dict())
