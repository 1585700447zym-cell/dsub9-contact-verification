"""Training components at complete episode/update boundaries; no physics launcher."""
from copy import deepcopy
import math
import numpy as np
import torch
from .five_axis_contract import VERSION, validate_config, permission
from .five_axis_sac import FiveAxisUpdater
from .five_axis_replay import FiveAxisReplay
from .sac_checkpoint import _same, _tensor, _optimizer, _rng


class FiveAxisTrainer:
    def __init__(self, config):
        self.config = validate_config(config)
        self.updater = FiveAxisUpdater(self.config)
        self.replay = FiveAxisReplay(capacity=self.config['learning']['replay_capacity'])
        seed = self.config['learning']['seed']
        self.warm_rng = np.random.default_rng(seed + 1)
        self.replay_rng = np.random.default_rng(seed + 2)
        self.policy_calls = self.warmup_draws = self.update_attempts = 0
        self.history = []; self.active_episode = False

    def action(self, observation, *, deterministic=False, warmup=False):
        if self.updater.failed: raise RuntimeError('Failed trainer')
        if not permission(observation): return np.zeros(5)
        if warmup:
            self.warmup_draws += 1
            return self.warm_rng.uniform(-1., 1., 5)
        self.policy_calls += 1
        return self.updater.predict(observation, deterministic=deterministic)[0]

    def publish(self, episode_id, rows, *, outcome, training_admitted):
        if self.active_episode or self.updater.failed:
            raise RuntimeError('Healthy complete publication boundary required')
        return self.replay.publish(episode_id, rows, outcome=outcome, training_admitted=training_admitted)

    def collect(self, session, case, *, seed=None, max_cycles=13500, deterministic=False, warmup=False):
        from .five_axis_collection import collect_episode, CollectionError
        if self.active_episode or self.updater.failed:
            raise RuntimeError('Healthy idle trainer required')
        self.active_episode = True
        before_calls, before_draws = self.policy_calls, self.warmup_draws
        try:
            raw = collect_episode(session, case, seed=seed, max_cycles=max_cycles,
                policy=lambda observation: self.action(observation, deterministic=deterministic, warmup=warmup))
            raw.update(policy_calls=self.policy_calls - before_calls,
                       warmup_draws=self.warmup_draws - before_draws)
            return raw
        except CollectionError as exc:
            exc.archive.update(policy_calls=self.policy_calls - before_calls,
                               warmup_draws=self.warmup_draws - before_draws)
            raise
        finally:
            self.active_episode = False

    def update_from_replay(self):
        if self.active_episode or self.updater.failed:
            raise RuntimeError('Healthy episode boundary required')
        batch = self.replay.sample(self.config['learning']['batch_size'], rng=self.replay_rng)
        self.update_attempts += 1
        result = self.updater.update(batch)
        self.history.append(deepcopy(result))
        return result

    def state_dict(self):
        if self.active_episode or self.updater.failed or self.update_attempts != self.updater.counts['critic']:
            raise RuntimeError('Healthy complete checkpoint boundary required')
        return deepcopy(dict(version=VERSION, config=self.config, updater=self.updater._snapshot(),
            replay=self.replay.state_dict(), warm_rng=self.warm_rng.bit_generator.state,
            replay_rng=self.replay_rng.bit_generator.state, policy_calls=self.policy_calls,
            warmup_draws=self.warmup_draws, update_attempts=self.update_attempts, history=self.history))

    def load_state_dict(self, state):
        expected = {'version', 'config', 'updater', 'replay', 'warm_rng', 'replay_rng',
                    'policy_calls', 'warmup_draws', 'update_attempts', 'history'}
        if (not isinstance(state, dict) or set(state) != expected or state['version'] != VERSION
                or not _same(state['config'], self.config) or self.active_episode):
            raise ValueError('Matching complete five-axis checkpoint required')
        candidate = FiveAxisTrainer(self.config)
        saved = state['updater']; template = candidate.updater._snapshot()
        if not isinstance(saved, dict) or set(saved) != set(template) or set(saved['counts']) != set(template['counts']):
            raise ValueError('Incomplete updater snapshot')
        counts = saved['counts']
        integers = list(counts.values()) + [state[key] for key in ('policy_calls', 'warmup_draws', 'update_attempts')]
        if any(type(value) is not int or value < 0 for value in integers):
            raise ValueError('Invalid checkpoint counters')
        if (counts['target'] != counts['critic'] or counts['actor'] != counts['temperature']
                or counts['actor'] > counts['critic'] or state['update_attempts'] != counts['critic']
                or not isinstance(state['history'], list) or len(state['history']) != counts['critic']):
            raise ValueError('Update counts/history differ')
        history_fields = {'critic_loss', 'actor_loss', 'temperature_loss', 'active_rows',
                          'batch_rows', 'alpha_after', 'critic_batches'}
        for row in state['history']:
            if (not isinstance(row, dict) or set(row) != history_fields
                    or type(row['batch_rows']) is not int or row['batch_rows'] != self.config['learning']['batch_size']
                    or type(row['active_rows']) is not int or not 0 <= row['active_rows'] <= row['batch_rows']
                    or type(row['critic_batches']) is not int):
                raise ValueError('Invalid diagnostic history fields/counts')
            for name in ('critic_loss', 'alpha_after', 'actor_loss', 'temperature_loss'):
                value = row[name]
                if name in ('actor_loss', 'temperature_loss') and row['active_rows'] == 0:
                    if value is not None: raise ValueError('Inactive diagnostic loss must be absent')
                elif type(value) not in (int, float) or not math.isfinite(value):
                    raise ValueError('Finite diagnostic loss/temperature required')
            if row['alpha_after'] <= 0 or row['critic_loss'] < 0:
                raise ValueError('Invalid diagnostic temperature/critic loss')
        if (sum(row['active_rows'] > 0 for row in state['history']) != counts['actor']
                or any(row['critic_batches'] != i for i, row in enumerate(state['history'], 1))):
            raise ValueError('Actor/update history differs')
        if saved['policy'].keys() != template['policy'].keys():
            raise ValueError('Incomplete policy/target state')
        for key, value in template['policy'].items(): _tensor(saved['policy'][key], value)
        _tensor(saved['alpha'], template['alpha']); _tensor(saved['rng'], template['rng'])
        torch.Generator().set_state(saved['rng'])
        for key, optimizer in zip(('critic', 'actor', 'temperature'), candidate.updater._optimizers()):
            _optimizer(saved[key], optimizer, counts[key])
        candidate.updater._restore(deepcopy(saved)); candidate.updater._finite_state()
        candidate.replay.load_state_dict(state['replay'])
        candidate.warm_rng = _rng(state['warm_rng']); candidate.replay_rng = _rng(state['replay_rng'])
        for key in ('policy_calls', 'warmup_draws', 'update_attempts', 'history'):
            setattr(candidate, key, deepcopy(state[key]))
        self.__dict__.update(candidate.__dict__)
