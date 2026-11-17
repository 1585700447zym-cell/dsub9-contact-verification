"""Continuous windows from whole five-axis episodes admitted by an external audit.

Starts are uniform over stored transitions (with replacement), including the
final transition. Each sample stays within one episode and carries its original
cycle indices. The trainer owns the NumPy sampling RNG and checkpoints its state.
"""
from dataclasses import dataclass

import numpy as np
import torch

from .audited_replay import ReplayBatch, _State
from .five_axis_contract import ACTION_DIM, WIDTH
from .five_axis_replay import FiveAxisReplay


_TRANSITION_FIELDS = tuple(k for k in ReplayBatch.__dataclass_fields__
                           if k not in ('observations', 'next_observations'))
_FLAGS = {'terminated', 'truncated', 'action_active', 'next_action_active'}
VERSION = 'five_axis_recovery_sequence_replay_v1'


@dataclass(frozen=True)
class SequenceReplayBatch:
    observations: torch.Tensor
    observation_valid_mask: torch.Tensor
    actions: torch.Tensor
    rewards: torch.Tensor
    discounts: torch.Tensor
    dt: torch.Tensor
    terminated: torch.Tensor
    truncated: torch.Tensor
    action_active: torch.Tensor
    next_action_active: torch.Tensor
    valid_mask: torch.Tensor
    learn_mask: torch.Tensor
    episode_ids: tuple[str, ...]
    start_cycles: tuple[int, ...]
    prefix_lengths: tuple[int, ...]
    burn_in: int

    def validate(self):
        """Check provenance, padding boundaries and five-axis physics field semantics."""
        from .five_axis_sac import validate_batch

        if not isinstance(self.actions, torch.Tensor) or self.actions.ndim != 3:
            raise ValueError('Sequence actions must have batch, time and action dimensions')
        b, t, _ = self.actions.shape
        if not b or type(self.burn_in) is not int or not 0 <= self.burn_in < t:
            raise ValueError('Nonempty batch and learning suffix required')
        for name in ('observations', 'observation_valid_mask', 'valid_mask', 'learn_mask', *_TRANSITION_FIELDS):
            value = getattr(self, name)
            width = WIDTH if name == 'observations' else ACTION_DIM if name == 'actions' else 1
            time = t + 1 if name in ('observations', 'observation_valid_mask') else t
            dtype = torch.bool if name in _FLAGS or name.endswith('_mask') else torch.float32
            if (not isinstance(value, torch.Tensor) or value.shape != (b, time, width)
                    or value.device.type != 'cpu' or value.dtype != dtype or value.requires_grad
                    or not torch.isfinite(value).all()):
                raise ValueError(f'Invalid sequence tensor {name}')
        metadata = (self.episode_ids, self.start_cycles, self.prefix_lengths)
        if any(not isinstance(items, tuple) or len(items) != b for items in metadata):
            raise ValueError('One source ID, start and prefix length required per window')
        for key, start, prefix in zip(*metadata):
            if (not isinstance(key, str) or not key or type(start) is not int or start < 0
                    or type(prefix) is not int or prefix != min(start, self.burn_in)):
                raise ValueError('Sequence source or prefix mismatch')

        # Valid observations enclose the real transitions and their extra next frame.
        first = self.burn_in - torch.tensor(self.prefix_lengths)[:, None]
        end = self.burn_in + self.learn_mask[:, :, 0].sum(dim=1, keepdim=True)
        steps = torch.arange(t + 1)[None, :]
        obs_valid = (steps >= first) & (steps <= end)
        valid = obs_valid[:, :-1] & obs_valid[:, 1:]
        learn = valid & (steps[:, :-1] >= self.burn_in)
        if (not learn.any(dim=1).all() or not torch.equal(self.observation_valid_mask[:, :, 0], obs_valid)
                or not torch.equal(self.valid_mask[:, :, 0], valid)
                or not torch.equal(self.learn_mask[:, :, 0], learn)):
            raise ValueError('Invalid observation, transition or learning window mask')
        # A short suffix must end at a terminal transition. A full suffix may
        # end at the boundary or in the middle of its episode.
        terminal = self.terminated[:, :, 0] & valid
        last = steps[:, :-1] == end - 1
        if ((terminal & ~last).any() or ((end < t) & last & ~terminal).any()
                or (self.truncated[:, :, 0] & valid).any()):
            raise ValueError('Unexpected boundary or externally cut recovery episode')

        validate_batch(ReplayBatch(
            observations=self.observations[:, :-1][valid],
            next_observations=self.observations[:, 1:][valid],
            **{name: getattr(self, name)[valid] for name in _TRANSITION_FIELDS},
        ))


def _compact(arrays):
    """Adjacent next/current observations were checked at the publication boundary."""
    frames = np.concatenate((arrays['observations'], arrays['next_observations'][-1:]))
    frames.setflags(write=False)
    return dict(frames=frames, **{name: arrays[name] for name in _TRANSITION_FIELDS})


class RecurrentReplay(FiveAxisReplay):
    """Only complete, reviewed task outcomes can contribute learning windows."""

    def _prepare(self, rows):
        arrays = super()._prepare(rows)
        if arrays['truncated'].any():
            raise ValueError('Externally truncated recovery episodes cannot enter replay')
        return _compact(arrays)

    def sample(self, *args, **kwargs):
        raise TypeError('Recurrent replay requires sample_sequences and continuous history')

    def sample_sequences(self, batch_size, burn_in, learn_steps, rng):
        if any(type(value) is not int for value in (batch_size, burn_in, learn_steps)):
            raise ValueError('Integer batch, burn-in and learning lengths required')
        if batch_size <= 0 or burn_in < 0 or learn_steps <= 0:
            raise ValueError('Invalid sequence sampling dimensions')
        if not isinstance(rng, np.random.Generator):
            raise ValueError('An explicit NumPy sampling generator is required')
        state = self._state
        if not state.size:
            raise RuntimeError('No audited experience')
        ends = np.cumsum([len(arrays['rewards']) for _, arrays in state.episodes])
        offsets = rng.integers(0, state.size, size=batch_size)
        owners = np.searchsorted(ends, offsets, side='right')
        starts = offsets - np.r_[0, ends[:-1]][owners]
        return self.sample_sequences_from_starts(
            tuple(state.episodes[owner][0] for owner in owners), tuple(map(int, starts)), burn_in, learn_steps)

    def sample_sequences_from_starts(self, episode_ids, start_cycles, burn_in, learn_steps):
        """Build the same contiguous windows from externally selected, checked starts.

        This does not grant admission or alter replay/RNG state. Opt-in samplers
        can select starts without replacing the legacy uniform distribution.
        """
        if (type(burn_in) is not int or burn_in < 0 or type(learn_steps) is not int or learn_steps <= 0
                or not isinstance(episode_ids, (tuple, list)) or not episode_ids
                or not isinstance(start_cycles, (tuple, list)) or len(episode_ids) != len(start_cycles)):
            raise ValueError('Valid explicit sequence sources and lengths required')
        episodes = dict(self._state.episodes)
        for key, start in zip(episode_ids, start_cycles):
            if (not isinstance(key, str) or key not in episodes or type(start) is not int
                    or not 0 <= start < len(episodes[key]['rewards'])):
                raise ValueError('Explicit window starts must belong to retained replay episodes')
        batch_size = len(episode_ids)
        starts = tuple(start_cycles)
        keys = tuple(episode_ids)
        t = burn_in + learn_steps
        frames = np.zeros((batch_size, t + 1, WIDTH), dtype=np.float32)
        obs_valid = np.zeros((batch_size, t + 1, 1), dtype=np.bool_)
        valid = np.zeros((batch_size, t, 1), dtype=np.bool_)
        learn = np.zeros_like(valid)
        values = {name: np.zeros((batch_size, t, ACTION_DIM if name == 'actions' else 1),
                                 dtype=np.bool_ if name in _FLAGS else np.float32)
                  for name in _TRANSITION_FIELDS}
        episode_ids, prefixes = [], []
        for row, (key, start) in enumerate(zip(keys, starts)):
            arrays = episodes[key]
            prefix = min(start, burn_in)
            source_start = start - prefix
            source_end = min(len(arrays['rewards']), start + learn_steps)
            dest_start = burn_in - prefix
            dest_end = burn_in + source_end - start
            frames[row, dest_start:dest_end+1] = arrays['frames'][source_start:source_end+1]
            for name in _TRANSITION_FIELDS:
                values[name][row, dest_start:dest_end] = arrays[name][source_start:source_end]
            obs_valid[row, dest_start:dest_end+1] = True
            valid[row, dest_start:dest_end] = True
            learn[row, burn_in:dest_end] = True
            episode_ids.append(key)
            prefixes.append(prefix)
        return SequenceReplayBatch(
            observations=torch.from_numpy(frames), observation_valid_mask=torch.from_numpy(obs_valid),
            valid_mask=torch.from_numpy(valid), learn_mask=torch.from_numpy(learn),
            episode_ids=tuple(episode_ids), start_cycles=tuple(map(int, starts)),
            prefix_lengths=tuple(prefixes), burn_in=burn_in,
            **{name: torch.from_numpy(value) for name, value in values.items()},
        )

    def state_dict(self):
        return dict(version=VERSION, capacity=self.capacity, seen=sorted(self._state.seen),
                    episodes=[(key, {name: torch.from_numpy(value.copy()) for name, value in arrays.items()})
                              for key, arrays in self._state.episodes])

    def load_state_dict(self, state):
        if (not isinstance(state, dict) or set(state) != {'version', 'capacity', 'seen', 'episodes'}
                or state['version'] != VERSION or type(state['capacity']) is not int
                or state['capacity'] != self.capacity or not isinstance(state['episodes'], list)):
            raise ValueError('Matching recurrent replay checkpoint required')
        # Adapt compact frames to the established 140/5 validator. All work is
        # done in a candidate, so even a bad last episode leaves live replay intact.
        episodes = []
        for entry in state['episodes']:
            if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                raise ValueError('Invalid recurrent replay episode entry')
            key, tensors = entry
            if not isinstance(tensors, dict) or set(tensors) != {'frames', *_TRANSITION_FIELDS}:
                raise ValueError('Incomplete recurrent replay episode fields')
            frames = tensors['frames']
            if (not isinstance(frames, torch.Tensor) or frames.ndim != 2
                    or frames.shape[1] != WIDTH or len(frames) < 2):
                raise ValueError('Recurrent episode requires adjacent observations')
            episodes.append((key, dict(observations=frames[:-1], next_observations=frames[1:],
                                       **{name: tensors[name] for name in _TRANSITION_FIELDS})))
        legacy = FiveAxisReplay(capacity=self.capacity)
        legacy.load_state_dict(dict(state, version='five_axis_replay_v1', episodes=episodes))
        candidate = legacy._state
        if any(arrays['truncated'].any() for _, arrays in candidate.episodes):
            raise ValueError('Truncation found in admitted recovery checkpoint')
        self._state = _State(tuple((key, _compact(arrays)) for key, arrays in candidate.episodes),
                             candidate.seen, candidate.size)
