"""Single-owner, in-memory, whole-episode replay; not an SB3 ReplayBuffer.

Publish only after external whole-episode AND training-admission audits. This
module checks their explicit booleans; it does not grant/certify admission.
All validation/allocation precedes one state replacement. No per-row insertion,
concurrent writers, disk durability, or trainer/checkpoint implementation.
Capacity evicts oldest WHOLE episodes. Explicitly audit-rejected and evicted IDs
remain consumed for this object's lifetime; callers retain the complete attempt
ledger. A validation/allocation exception leaves state and IDs unchanged so the
caller can retry the transaction; that is not permission to sanitize bad physics.
"""
from dataclasses import dataclass
import math
import numbers

import numpy as np
import torch

from .action import normalized_action
from .episode_buffer import _archive


@dataclass(frozen=True)
class ReplayBatch:
    observations: torch.Tensor
    next_observations: torch.Tensor
    actions: torch.Tensor
    rewards: torch.Tensor
    discounts: torch.Tensor
    dt: torch.Tensor
    terminated: torch.Tensor
    truncated: torch.Tensor
    action_active: torch.Tensor
    next_action_active: torch.Tensor


@dataclass(frozen=True)
class _State:
    episodes: tuple = ()
    seen: frozenset = frozenset()
    size: int = 0


def _boolean(value):
    if type(value) not in (bool, np.bool_):
        raise ValueError('Audit and transition flags must be boolean')
    return bool(value)


def _number(value):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, numbers.Real):
        raise ValueError('Expected finite numeric scalar')
    value = float(value)
    if not math.isfinite(value):
        raise ValueError('Expected finite numeric scalar')
    return value


class AuditedReplay:
    def __init__(self, *, capacity):
        if type(capacity) is not int or capacity <= 0:
            raise ValueError('capacity must be a positive integer')
        self.capacity = capacity
        self._state = _State()

    def __len__(self):
        return self._state.size

    @property
    def episode_ids(self):
        return tuple(key for key, _ in self._state.episodes)

    def _prepare(self, rows):
        if not rows or len(rows) > self.capacity:
            raise ValueError('Complete nonempty episode must fit capacity')
        arrays = {name: [] for name in ReplayBatch.__dataclass_fields__}
        previous = None
        for i, row in enumerate(rows):
            if not isinstance(row, dict) or not _archive(row)[1]:
                raise ValueError('Nonfinite or unarchivable episode data')
            try:
                flags = {name: _boolean(row[name]) for name in
                         ('terminated', 'truncated', 'action_active', 'next_action_active')}
                boundary = flags['terminated'] or flags['truncated']
                if flags['terminated'] and flags['truncated'] or boundary != (i == len(rows) - 1):
                    raise ValueError('Exactly one final episode boundary required')
                obs, nxt = [np.asarray(row[name]) for name in ('observation', 'next_observation')]
                if any(a.shape != (120,) or a.dtype.kind not in 'iuf' or
                       not np.all(np.isfinite(a)) or np.any(a < -10) or np.any(a > 10) for a in (obs, nxt)):
                    raise ValueError('Expected finite 120-vector in observation bounds')
                if previous is not None and (not np.array_equal(previous[0], obs) or
                                             previous[1] != flags['action_active']):
                    raise ValueError('Discontinuous episode observation or permission')
                action = normalized_action(row['action'])
                if not flags['action_active']:
                    action = np.zeros(4)
                dt, discount, reward = [_number(row[name]) for name in ('dt', 'discount', 'reward')]
                if dt <= 0 or not 0 < discount <= 1 or not math.isclose(
                        discount, math.exp(-dt / 10), rel_tol=0, abs_tol=1e-12):
                    raise ValueError('Discount must match positive dt and v3 time constant 10s')
            except KeyError as exc:
                raise ValueError(f'Missing transition field: {exc}') from exc
            values = dict(observations=obs, next_observations=nxt, actions=action,
                          rewards=[reward], discounts=[discount], dt=[dt],
                          **{k: [v] for k, v in flags.items()})
            for name, value in values.items():
                arrays[name].append(value)
            previous = (nxt, flags['next_action_active'])
        prepared = {}
        for name, values in arrays.items():
            dtype = np.bool_ if name in flags else np.float32
            with np.errstate(over='ignore'):
                array = np.array(values, dtype=dtype)
            if not np.all(np.isfinite(array)):
                raise ValueError('Episode cannot be represented in finite training tensors')
            array.setflags(write=False)
            prepared[name] = array
        return prepared

    def publish(self, episode_id, rows, *, outcome, training_admitted):
        state = self._state
        if not isinstance(episode_id, str) or not episode_id:
            raise ValueError('Nonempty episode_id required')
        if episode_id in state.seen:
            raise RuntimeError('Episode already finalized; cannot replay or promote it')
        if not isinstance(rows, (list, tuple)) or not isinstance(outcome, dict):
            raise ValueError('Rows and audit outcome required')
        flags = [_boolean(training_admitted)]
        flags.extend(_boolean(outcome.get(key, False)) for key in
                     ('simulation_valid', 'physical_stopped', 'valid_for_learning'))
        seen = state.seen | {episode_id}
        if not all(flags):
            result = dict(committed=0, discarded=len(rows), evicted=0)
            new_state = _State(state.episodes, seen, state.size)
        else:
            prepared = self._prepare(rows)
            episodes, size = list(state.episodes), state.size
            while size + len(rows) > self.capacity:
                _, old = episodes.pop(0)
                size -= len(old['rewards'])
            result = dict(committed=len(rows), discarded=0, evicted=state.size - size)
            new_state = _State(tuple(episodes) + ((episode_id, prepared),), seen, size + len(rows))
        self._state = new_state  # The only visible mutation: all-or-none publication.
        return result

    def sample(self, batch_size, *, rng, device='cpu'):
        if type(batch_size) is not int or batch_size <= 0:
            raise ValueError('batch_size must be a positive integer')
        state = self._state
        if not state.size:
            raise RuntimeError('No audited experience')
        indices = rng.integers(0, state.size, size=batch_size)
        ends = np.cumsum([len(arrays['rewards']) for _, arrays in state.episodes])
        owners = np.searchsorted(ends, indices, side='right')
        starts = np.r_[0, ends[:-1]]
        # Only gather the requested batch, never concatenate/copy the whole pool.
        values = {name: torch.tensor(np.stack([
            state.episodes[owner][1][name][index - starts[owner]]
            for owner, index in zip(owners, indices)]), device=device)
            for name in ReplayBatch.__dataclass_fields__}
        return ReplayBatch(**values)
