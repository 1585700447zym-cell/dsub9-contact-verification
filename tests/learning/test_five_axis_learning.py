"""Synthetic tensors and full component resume; never performs task training."""
from copy import deepcopy
from dataclasses import replace
import importlib
import math
import numpy as np
import pytest
import torch
from tests.learning.test_five_axis_interface import api, fixture
from tools.learning.audited_replay import ReplayBatch
from tools.learning.sac_checkpoint import _same


def obs(active=True):
    controller, snap, context, profile = fixture('SEARCH' if active else 'UNLOAD', active)
    return api('observation').FiveAxisObservation(snap.state, controller.config, profile).capture(snap, context)[0]


def rows():
    x, y = obs(), obs(False)
    return [dict(observation=x.tolist(), next_observation=x.tolist(), action=[.1] * 5,
        reward=-.01, dt=.002, discount=math.exp(-.002 / 10), terminated=False, truncated=False,
        action_active=True, next_action_active=True),
        dict(observation=x.tolist(), next_observation=y.tolist(), action=[.1] * 5,
        reward=9.99, dt=.002, discount=math.exp(-.002 / 10), terminated=True, truncated=False,
        action_active=True, next_action_active=False)]


OUTCOME = dict(simulation_valid=True, physical_stopped=True, valid_for_learning=True)


def batch(active=True):
    n = 8
    return ReplayBatch(observations=torch.tensor(np.tile(obs(active), (n, 1))),
        next_observations=torch.tensor(np.tile(obs(False), (n, 1))),
        actions=torch.full((n, 5), .1 if active else 0.), rewards=torch.full((n, 1), -.01),
        discounts=torch.full((n, 1), math.exp(-.002 / 10)), dt=torch.full((n, 1), .002),
        terminated=torch.zeros((n, 1), dtype=torch.bool), truncated=torch.zeros((n, 1), dtype=torch.bool),
        action_active=torch.full((n, 1), active), next_action_active=torch.zeros((n, 1), dtype=torch.bool))


def test_five_axis_update_changes_both_q_actor_alpha_and_target():
    u = api('sac').FiveAxisUpdater(api('contract').learning_config())
    before = u.fingerprints()
    old_target = [p.detach().clone() for p in u.policy.critic_target.parameters()]
    stats = u.update(batch())
    assert u.policy.action_space.shape == (5,) and u.policy.observation_space.shape == (140,)
    assert all(before[k] != u.fingerprints()[k] for k in before)
    assert stats['active_rows'] == 8
    for old, q, target in zip(old_target, u.policy.critic.parameters(), u.policy.critic_target.parameters()):
        torch.testing.assert_close(target, .995 * old + .005 * q.detach(), rtol=1e-6, atol=1e-7)
    for network in u.policy.critic.q_networks:
        assert all(u.policy.critic.optimizer.state[p]['step'] == 1 for p in network.parameters())


def test_inactive_rows_do_not_move_actor_or_temperature_with_existing_adam_momentum():
    u = api('sac').FiveAxisUpdater(api('contract').learning_config())
    u.update(batch()); before = u._snapshot(); u.update(batch(False)); after = u._snapshot()
    for key in ('actor', 'temperature', 'alpha'):
        assert _same(before[key], after[key])
    for key in before['policy']:
        if key.startswith('actor.'):
            assert torch.equal(before['policy'][key], after['policy'][key])
    assert u.counts == dict(critic=2, actor=1, temperature=1, target=2)


def test_inactive_next_action_is_five_zeros_and_has_no_entropy_bootstrap(monkeypatch):
    u = api('sac').FiveAxisUpdater(api('contract').learning_config())
    data = batch(False); data.terminated[0] = True; data.truncated[1] = True
    observed = []
    def target_q(observations, actions):
        observed.append(actions.clone())
        return torch.full((len(actions), 1), 3.), torch.full((len(actions), 1), 5.)
    monkeypatch.setattr(u.policy.critic_target, 'forward', target_q)
    target = u.targets(data)
    assert observed[0].shape == (8, 5) and not observed[0].any()
    assert target[0].item() == pytest.approx(-.01)
    torch.testing.assert_close(target[1:], data.rewards[1:] + 3 * data.discounts[1:])


def test_bad_legacy_batch_rolls_back_all_state_and_latches_failure():
    u = api('sac').FiveAxisUpdater(api('contract').learning_config())
    before = u._snapshot()
    with pytest.raises(ValueError): u.update(replace(batch(), actions=torch.zeros((8, 4))))
    assert u.failed and _same(before, u._snapshot())
    with pytest.raises(RuntimeError): u.predict(obs(), deterministic=True)


def test_whole_episode_replay_checks_dimensions_permissions_continuity_and_seen_ids():
    replay = api('replay').FiveAxisReplay(capacity=2)
    bad = rows(); bad[0]['action'] = [.1] * 4
    with pytest.raises(ValueError): replay.publish('bad', bad, outcome=OUTCOME, training_admitted=True)
    assert not len(replay)
    bad = rows(); bad[1]['observation'][24] += .1
    with pytest.raises(ValueError): replay.publish('gap', bad, outcome=OUTCOME, training_admitted=True)
    replay.publish('one', rows(), outcome=OUTCOME, training_admitted=True)
    replay.publish('two', rows(), outcome=OUTCOME, training_admitted=True)
    assert replay.episode_ids == ('two',) and len(replay) == 2
    with pytest.raises(RuntimeError): replay.publish('one', rows(), outcome=OUTCOME, training_admitted=True)


def test_ineligible_episode_stays_out_of_replay():
    replay = api('replay').FiveAxisReplay(capacity=10)
    result = replay.publish('invalid', rows(), outcome=dict(OUTCOME, simulation_valid=False), training_admitted=True)
    assert result['committed'] == 0 and not len(replay)


def test_terminal_transition_cannot_claim_a_future_active_policy():
    replay = api('replay').FiveAxisReplay(capacity=10)
    data = rows(); data[-1]['next_observation'] = obs().tolist(); data[-1]['next_action_active'] = True
    with pytest.raises(ValueError):
        replay.publish('terminal-active', data, outcome=OUTCOME, training_admitted=True)
    assert not len(replay)
    u = api('sac').FiveAxisUpdater(api('contract').learning_config())
    data = batch(); data.terminated[0] = True
    data.next_observations[0] = torch.tensor(obs()); data.next_action_active[0] = True
    with pytest.raises(ValueError): u.update(data)


def test_full_checkpoint_restores_next_sample_action_and_update_exactly(tmp_path):
    training = api('training'); checkpoints = api('checkpoint')
    config = api('contract').learning_config()
    config['learning'].update(batch_size=8, replay_capacity=20)
    original = training.FiveAxisTrainer(config)
    original.publish('synthetic', rows(), outcome=OUTCOME, training_admitted=True)
    original.update_from_replay()
    original.action(obs()); original.action(obs(), warmup=True)
    target = tmp_path / 'five-axis'
    digest = checkpoints.save_checkpoint(original, target)
    restored = checkpoints.load_checkpoint(target, expected_digest=digest, config=config)
    assert _same(original.state_dict(), restored.state_dict())
    np.testing.assert_array_equal(original.action(obs()), restored.action(obs()))
    np.testing.assert_array_equal(original.action(obs(), warmup=True), restored.action(obs(), warmup=True))
    assert original.update_from_replay() == restored.update_from_replay()
    assert _same(original.state_dict(), restored.state_dict())
    with pytest.raises(FileExistsError): checkpoints.save_checkpoint(original, target)
    with pytest.raises(ValueError): checkpoints.load_checkpoint(target, expected_digest='0' * 64, config=config)


def test_checkpoint_rejects_old_or_incomplete_state_without_mutating_live_trainer():
    trainer = api('training').FiveAxisTrainer(api('contract').learning_config())
    before = trainer.state_dict()
    wrong = deepcopy(before); wrong['version'] = 'v4_checkpoint_v1'
    with pytest.raises(ValueError): trainer.load_state_dict(wrong)
    wrong = deepcopy(before); del wrong['warm_rng']
    with pytest.raises(ValueError): trainer.load_state_dict(wrong)
    assert _same(before, trainer.state_dict())


def test_inactive_policy_permission_returns_five_zeros_without_network_call():
    trainer = api('training').FiveAxisTrainer(api('contract').learning_config())
    before = trainer.policy_calls
    assert trainer.action(obs(False)).tolist() == [0.] * 5
    assert trainer.policy_calls == before
