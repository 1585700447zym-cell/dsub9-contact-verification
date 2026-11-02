"""Whole-episode replay for 140/5; external physics/admission audits remain required."""
from copy import deepcopy
import math
import numpy as np
import torch
from .audited_replay import AuditedReplay, ReplayBatch, _State, _boolean, _number
from .episode_buffer import _archive
from .five_axis_action import normalized_action
from .five_axis_contract import permission


class FiveAxisReplay(AuditedReplay):
    def _prepare(self, rows):
        if not rows or len(rows) > self.capacity:
            raise ValueError('Complete nonempty episode must fit replay')
        arrays = {key: [] for key in ReplayBatch.__dataclass_fields__}; previous = None
        for index, row in enumerate(rows):
            if not isinstance(row, dict) or not _archive(row)[1]:
                raise ValueError('Finite serializable transition required')
            flags = {key: _boolean(row[key]) for key in
                     ('terminated', 'truncated', 'action_active', 'next_action_active')}
            if ((flags['terminated'] and flags['truncated'])
                    or (flags['terminated'] or flags['truncated']) != (index == len(rows) - 1)):
                raise ValueError('Exactly one final boundary required')
            if flags['terminated'] and flags['next_action_active']:
                raise ValueError('Terminal observation cannot enable a future policy')
            obs, nxt = [np.asarray(row[key]) for key in ('observation', 'next_observation')]
            if permission(obs) != flags['action_active'] or permission(nxt) != flags['next_action_active']:
                raise ValueError('Observation/permission mismatch')
            if previous is not None and (not np.array_equal(previous[0], obs) or previous[1] != flags['action_active']):
                raise ValueError('Discontinuous episode')
            action = normalized_action(row['action'])
            if not flags['action_active'] and np.any(action):
                raise ValueError('Inactive experience action must be zero')
            dt, discount, reward = [_number(row[key]) for key in ('dt', 'discount', 'reward')]
            if dt <= 0 or not 0 < discount <= 1 or not math.isclose(discount, math.exp(-dt / 10), abs_tol=1e-12, rel_tol=0):
                raise ValueError('Physical-time discount mismatch')
            values = dict(observations=obs, next_observations=nxt, actions=action, rewards=[reward],
                discounts=[discount], dt=[dt], **{key: [value] for key, value in flags.items()})
            for key, value in values.items(): arrays[key].append(value)
            previous = nxt, flags['next_action_active']
        result = {}
        for key, value in arrays.items():
            array = np.asarray(value, dtype=np.bool_ if key in flags else np.float32)
            if not np.isfinite(array).all(): raise ValueError('Unrepresentable replay data')
            array.setflags(write=False); result[key] = array
        return result

    def state_dict(self):
        return dict(version='five_axis_replay_v1', capacity=self.capacity,
            seen=sorted(self._state.seen), episodes=[(key, {name: torch.from_numpy(value.copy())
                for name, value in arrays.items()}) for key, arrays in self._state.episodes])

    def load_state_dict(self, state):
        from .five_axis_sac import validate_batch
        if (not isinstance(state, dict) or set(state) != {'version', 'capacity', 'seen', 'episodes'}
                or state['version'] != 'five_axis_replay_v1' or state['capacity'] != self.capacity
                or not isinstance(state['seen'], list) or not isinstance(state['episodes'], list)):
            raise ValueError('Five-axis replay snapshot required')
        seen = state['seen']
        if any(not isinstance(key, str) or not key for key in seen) or len(seen) != len(set(seen)):
            raise ValueError('Replay seen IDs invalid')
        episodes = []; size = 0; keys = set()
        for key, tensors in state['episodes']:
            if key not in seen or key in keys or set(tensors) != set(ReplayBatch.__dataclass_fields__):
                raise ValueError('Replay IDs or fields differ')
            batch = ReplayBatch(**tensors); validate_batch(batch); n = len(batch.observations)
            boundary = batch.terminated[:, 0] | batch.truncated[:, 0]
            if (not boundary[-1] or boundary[:-1].any()
                    or not torch.equal(batch.next_observations[:-1], batch.observations[1:])
                    or not torch.equal(batch.next_action_active[:-1], batch.action_active[1:])):
                raise ValueError('Replay continuity/final boundary invalid')
            arrays = {name: value.detach().numpy().copy() for name, value in tensors.items()}
            for value in arrays.values(): value.setflags(write=False)
            keys.add(key); size += n; episodes.append((key, arrays))
        if size > self.capacity: raise ValueError('Restored replay exceeds capacity')
        self._state = _State(tuple(episodes), frozenset(seen), size)
