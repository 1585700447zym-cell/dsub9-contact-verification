"""Sequence indices, provenance, permission masks and atomic checkpoint restoration."""
from dataclasses import replace
import math

import numpy as np
import pytest
import torch

from tools.learning.five_axis_contract import field_slices
from tools.learning.recurrent_replay import RecurrentReplay


def observation(value, active):
    fields = field_slices()
    obs = np.zeros(140, dtype=np.float32)
    for name, code in (('policy_phase', 2 if active else 1), ('physical_phase', 0),
                       ('recovery_phase', 0), ('decision', 0)):
        obs[fields[name].start + code] = 1
    obs[fields['action_active']] = active
    obs[fields['simulation_valid']] = True
    obs[0] = value
    return obs.tolist()


def episode(label, phases):
    frames = [observation(label + k / 10, active)
              for k, active in enumerate([*phases, False])]
    return [dict(observation=frames[k], next_observation=frames[k+1],
                 action=[0.25 if active else 0.] * 5, reward=label + k,
                 dt=0.002, discount=math.exp(-0.002 / 10), terminated=k+1 == len(phases),
                 truncated=False, action_active=active,
                 next_action_active=phases[k+1] if k+1 < len(phases) else False)
            for k, active in enumerate(phases)]


OUTCOME = dict(simulation_valid=True, physical_stopped=True, valid_for_learning=True)


def publish(replay, name, rows):
    return replay.publish(name, rows, training_admitted=True, outcome=OUTCOME)


def test_windows_follow_one_episode_and_include_last_next_frame_and_real_burn_in():
    replay = RecurrentReplay(capacity=8)
    sources = {'a': episode(1, [True, False]), 'b': episode(4, [False, True, True, False])}
    for name, rows in sources.items():
        publish(replay, name, rows)
    rng = np.random.default_rng(55)
    batch = replay.sample_sequences(24, 2, 3, rng)
    batch.validate()
    assert batch.observations.shape == (24, 6, 140)
    assert set(zip(batch.episode_ids, batch.start_cycles)) == {
        (name, cycle) for name, rows in sources.items() for cycle in range(len(rows))}
    for i, (name, start, prefix) in enumerate(zip(batch.episode_ids, batch.start_cycles, batch.prefix_lengths)):
        source = sources[name]
        assert prefix == min(start, 2)
        first = 2 - prefix
        rows = source[start-prefix:start+3]
        last = first + len(rows)
        assert batch.valid_mask[i, :, 0].tolist() == [first <= t < last for t in range(5)]
        assert batch.learn_mask[i, :, 0].tolist() == [2 <= t < last for t in range(5)]
        assert batch.observation_valid_mask[i, :, 0].tolist() == [first <= t <= last for t in range(6)]
        frames = [row['observation'] for row in rows] + [rows[-1]['next_observation']]
        torch.testing.assert_close(batch.observations[i, first:last+1], torch.tensor(frames))
        assert batch.terminated[i, last-1].item() == rows[-1]['terminated']
        assert batch.action_active[i, first:last, 0].tolist() == [row['action_active'] for row in rows]
        assert batch.rewards[i, first:last, 0].tolist() == [row['reward'] for row in rows]


def test_corrupt_mask_permission_or_boundary_is_rejected():
    replay = RecurrentReplay(capacity=8)
    publish(replay, 'a', episode(1, [True, False]))
    b = replay.sample_sequences(1, 0, 4, np.random.default_rng(1))
    for field, where, value in (('observation_valid_mask', 2, False), ('valid_mask', 0, False),
                                ('learn_mask', 0, False), ('action_active', 0, False),
                                ('terminated', 0, True), ('terminated', 1, False)):
        tensor = getattr(b, field).clone()
        tensor[0, where, 0] = value
        with pytest.raises(ValueError):
            replace(b, **{field: tensor}).validate()


def test_checkpoint_rejects_foreign_replay_and_preserves_eviction_and_seen_ids():
    replay = RecurrentReplay(capacity=3)
    publish(replay, 'first', episode(1, [True, False]))
    replay.publish('invalid', [], outcome=OUTCOME, training_admitted=False)
    publish(replay, 'next', episode(2, [False, True]))
    assert replay.episode_ids == ('next',)
    state = replay.state_dict()
    restored = RecurrentReplay(capacity=3)
    restored.load_state_dict(state)
    a = replay.sample_sequences(2, 4, 5, np.random.default_rng(6))
    b = restored.sample_sequences(2, 4, 5, np.random.default_rng(6))
    for field in vars(a):
        lhs, rhs = getattr(a, field), getattr(b, field)
        assert torch.equal(lhs, rhs) if isinstance(lhs, torch.Tensor) else lhs == rhs
    for name in ('first', 'invalid', 'next'):
        with pytest.raises(RuntimeError):
            publish(restored, name, episode(1, [True]))
    with pytest.raises(ValueError):
        restored.load_state_dict(dict(state, version='five_axis_replay_v1'))
    state['episodes'][0][1]['action_active'][0] = True
    with pytest.raises(ValueError):
        restored.load_state_dict(state)
    assert restored.episode_ids == ('next',)
    assert torch.equal(restored.state_dict()['episodes'][0][1]['action_active'],
                       replay.state_dict()['episodes'][0][1]['action_active'])


def test_external_cut_and_mismatched_transition_are_rejected_atomically():
    replay = RecurrentReplay(capacity=4)
    rows = episode(1, [True, False])
    rows[-1].update(terminated=False, truncated=True)
    with pytest.raises(ValueError):
        publish(replay, 'a', rows)
    rows = episode(1, [True, False])
    rows[1]['observation'] = observation(3, False)
    with pytest.raises(ValueError):
        publish(replay, 'a', rows)
    assert len(replay) == 0
    assert publish(replay, 'a', episode(1, [True, False]))['committed'] == 2
