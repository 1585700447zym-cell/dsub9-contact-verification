"""Synthetic protocol fixtures only: none of these rows are physical experience."""
import math

import numpy as np
import pytest
import torch


def episode(length=2, *, truncated=False):
    return [dict(observation=[i / 100] * 120, next_observation=[(i + 1) / 100] * 120,
        action=[.2, -.1, .3, -.4], reward=-.01, dt=.002,
        discount=math.exp(-.002 / 10), action_active=i % 2 == 0,
        next_action_active=(i + 1) % 2 == 0,
        terminated=i == length - 1 and not truncated,
        truncated=i == length - 1 and truncated) for i in range(length)]


def audit(**changes):
    return dict(dict(simulation_valid=True, physical_stopped=True,
                     valid_for_learning=True, task_outcome='CONTACT_GUARD'), **changes)


def publish(replay, key='synthetic-1', rows=None, **changes):
    return replay.publish(key, episode() if rows is None else rows,
                          outcome=audit(**changes), training_admitted=True)


def test_no_partial_publication_and_real_tensor_sample():
    from tools.learning.audited_replay import AuditedReplay
    replay = AuditedReplay(capacity=10)
    rows = episode()
    result = publish(replay, rows=rows)
    assert result == dict(committed=2, discarded=0, evicted=0)
    rows[0]['observation'][0] = 9
    batch = replay.sample(64, rng=np.random.default_rng(1))
    assert batch.observations.shape == (64, 120)
    assert batch.actions.shape == (64, 4)
    assert batch.rewards.shape == batch.discounts.shape == (64, 1)
    assert batch.terminated.dtype == batch.truncated.dtype == torch.bool
    assert batch.action_active.dtype == batch.next_action_active.dtype == torch.bool
    assert torch.all(batch.actions[~batch.action_active[:, 0]] == 0)
    assert batch.observations.max() < 1
    batch.observations.fill_(99)
    assert replay.sample(4, rng=np.random.default_rng(2)).observations.max() < 1


@pytest.mark.parametrize('field', ['simulation_valid', 'physical_stopped', 'valid_for_learning'])
def test_failed_audit_discards_every_row(field):
    from tools.learning.audited_replay import AuditedReplay
    replay = AuditedReplay(capacity=10)
    assert publish(replay, **{field: False})['discarded'] == 2
    assert len(replay) == 0


def test_candidate_cannot_be_promoted_by_finite_rows_or_task_success():
    from tools.learning.audited_replay import AuditedReplay
    replay = AuditedReplay(capacity=10)
    assert replay.publish('candidate', episode(), outcome=audit(task_outcome='SUCCESS'),
                          training_admitted=False)['committed'] == 0
    with pytest.raises(ValueError, match='boolean'):
        replay.publish('string', episode(), outcome=audit(), training_admitted='false')
    with pytest.raises(RuntimeError, match='already'):
        publish(replay, 'candidate')


@pytest.mark.parametrize('change', [
    {'reward': float('nan')}, {'dt': -1}, {'discount': .99}, {'dt': True},
    {'action': [0] * 6}, {'action': [float('inf')] * 4, 'action_active': False},
    {'observation': [0] * 119}, {'observation': [11] * 120},
    {'next_action_active': 'false'}, {'terminated': True, 'truncated': True},
    {'metadata': {'nonfinite': 'nan'}},
])
def test_bad_late_row_cannot_evict_or_publish_anything(change):
    from tools.learning.audited_replay import AuditedReplay
    replay = AuditedReplay(capacity=2)
    publish(replay, 'old')
    rows = episode()
    rows[-1].update(change)
    with pytest.raises(ValueError):
        publish(replay, 'bad', rows)
    assert len(replay) == 2 and replay.episode_ids == ('old',)


@pytest.mark.parametrize('bad_kind', ['empty', 'unfinished', 'early_end', 'discontinuous', 'mask_gap'])
def test_only_complete_contiguous_episodes_are_accepted(bad_kind):
    from tools.learning.audited_replay import AuditedReplay
    rows = episode()
    if bad_kind == 'empty': rows = []
    if bad_kind == 'unfinished': rows[-1]['terminated'] = False
    if bad_kind == 'early_end': rows[0]['truncated'] = True
    if bad_kind == 'discontinuous': rows[1]['observation'][3] = 1
    if bad_kind == 'mask_gap': rows[1]['action_active'] = True
    with pytest.raises(ValueError):
        publish(AuditedReplay(capacity=10), rows=rows)


def test_whole_episode_eviction_capacity_and_duplicate_retry(monkeypatch):
    from tools.learning.audited_replay import AuditedReplay
    replay = AuditedReplay(capacity=3)
    publish(replay, 'a')
    assert publish(replay, 'b')['evicted'] == 2
    assert replay.episode_ids == ('b',) and len(replay) == 2
    with pytest.raises(RuntimeError): publish(replay, 'a')
    with pytest.raises(ValueError): publish(replay, 'long', episode(4))
    original = replay._prepare
    def fail(rows): raise MemoryError('injected allocation failure')
    monkeypatch.setattr(replay, '_prepare', fail)
    with pytest.raises(MemoryError): publish(replay, 'retry')
    assert replay.episode_ids == ('b',)
    monkeypatch.setattr(replay, '_prepare', original)
    assert publish(replay, 'retry')['committed'] == 2


def test_truncation_bootstraps_true_cut_state_with_recorded_discount():
    from tools.learning.audited_replay import AuditedReplay
    from tools.learning.tensor_masks import critic_target
    replay = AuditedReplay(capacity=10)
    publish(replay, rows=episode(1, truncated=True))
    batch = replay.sample(1, rng=np.random.default_rng(0))
    assert batch.truncated.item() and not batch.terminated.item()
    torch.testing.assert_close(batch.next_observations, torch.full((1, 120), .01))
    target = critic_target(reward=batch.rewards, discount=batch.discounts,
        terminated=batch.terminated, q_next=torch.ones((1, 1)),
        log_probability=torch.full((1, 1), -5.), alpha=torch.tensor(.2),
        next_active=batch.next_action_active)
    torch.testing.assert_close(target, batch.rewards + batch.discounts)


@pytest.mark.parametrize('size', [0, -1, True])
def test_invalid_sampling_and_capacity(size):
    from tools.learning.audited_replay import AuditedReplay
    with pytest.raises(ValueError): AuditedReplay(capacity=size)
    replay = AuditedReplay(capacity=2)
    publish(replay)
    with pytest.raises(ValueError): replay.sample(size, rng=np.random.default_rng(0))


@pytest.mark.parametrize('dtype', [np.int8, np.int16, np.int32, np.int64])
def test_signed_minimum_cannot_overflow_observation_bounds(dtype):
    from tools.learning.audited_replay import AuditedReplay
    rows = episode(1)
    rows[0]['observation'] = np.full(120, np.iinfo(dtype).min, dtype=dtype)
    replay = AuditedReplay(capacity=2)
    with pytest.raises(ValueError, match='observation bounds'):
        publish(replay, rows=rows)
    assert len(replay) == 0
