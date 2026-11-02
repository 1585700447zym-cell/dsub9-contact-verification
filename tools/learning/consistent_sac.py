"""Fresh SAC for the repaired G1/30 s execution domain.

The frozen five-axis code supplies numerical kernels only. Its execution
configuration, checkpoints and collected experience are never admitted here.
Native episode admission remains the launcher's independent responsibility.
"""
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import uuid

import numpy as np
import torch

from tools.dynamics.reference_envelope import VERSION as REFERENCE_VERSION
from .five_axis_contract import (VERSION as NUMERICAL_KERNEL_VERSION,
    learning_config as _kernel_defaults)
from .five_axis_collection import (collect_episode as _collect_kernel,
                                    CollectionError)
from .five_axis_replay import FiveAxisReplay
from .five_axis_sac import FiveAxisUpdater
from .five_axis_training import FiveAxisTrainer
from .global_residual_action import profile_config
from .sac_checkpoint import _same

VERSION = 'consistent_reference_sac_G1_30s_v1'
STATE_VERSION = 'consistent_reference_sac_state_v1'
CHECKPOINT_VERSION = 'consistent_reference_sac_checkpoint_v1'


def execution_contract():
    contract = profile_config('G1')
    contract.update(version='global_residual_G1_30s_reference_consistent_v1',
                    reference_consistency_version=REFERENCE_VERSION)
    return contract


def learning_config():
    config = _kernel_defaults()
    contract = execution_contract()
    config.update(version=VERSION, observation_version=contract['observation_version'],
                  action_scale=deepcopy(contract['action_scale']), execution_contract=contract)
    config['learning']['replay_capacity'] = 192000
    return config


def validate_config(config):
    """This bounded trial freezes every learning and execution parameter."""
    if not _same(config, learning_config()):
        raise ValueError('Matching repaired G1/30-second SAC configuration required')
    return deepcopy(config)


def contract_digest(value):
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False,
                         allow_nan=False, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _numerical_config(config):
    """Private constructor inputs, never a claim about executed dynamics."""
    config = validate_config(config)
    numerical = _kernel_defaults()
    numerical['learning'] = deepcopy(config['learning'])
    return numerical


class ConsistentUpdater(FiveAxisUpdater):
    config_validator = staticmethod(validate_config)

    def __init__(self, config):
        accepted = validate_config(config)
        # Architecture, optimizer and RNG initialization are dimension-compatible.
        # Inherited update/rollback uses numerical settings, not the old dynamics.
        super().__init__(_numerical_config(accepted))
        self.config = accepted


def _bind_archive(raw, contract):
    raw.update(version=contract['version'], learning_version=VERSION,
        execution_contract=deepcopy(contract), collection_kernel_version=NUMERICAL_KERNEL_VERSION)
    # A reset fault can precede creation of the observation builder.
    raw.setdefault('observation_version', contract['observation_version'])
    return raw


def collect_episode(session, case, *, policy, seed=None, max_cycles=16000):
    contract = execution_contract()
    if not _same(getattr(session, 'contract', None), contract):
        raise ValueError('Collector requires the actual repaired G1/30-second session contract')
    if type(max_cycles) is not int or not 0 < max_cycles <= contract['max_cycles']:
        raise ValueError('Collection ceiling must be between 1 and 16000 cycles')
    try:
        raw = _collect_kernel(session, case, policy=policy, seed=seed, max_cycles=max_cycles)
    except CollectionError as exc:
        _bind_archive(exc.archive, contract)
        raise
    _bind_archive(raw, contract)
    if (not _same(getattr(session, 'contract', None), contract)
            or raw['observation_version'] != contract['observation_version']):
        raw['error'] = 'Execution/observation contract changed during collection'
        raise CollectionError(raw['error'], raw)
    return raw


_KERNEL_STATE_FIELDS = {'version', 'config', 'updater', 'replay', 'warm_rng',
    'replay_rng', 'policy_calls', 'warmup_draws', 'update_attempts', 'history'}
_STATE_FIELDS = _KERNEL_STATE_FIELDS | {'learning_version', 'execution_contract', 'numerical_kernel_version'}


class Trainer(FiveAxisTrainer):
    """Ordinary SAC with a fresh, separately bound complete component state."""
    def __init__(self, config):
        self.config = validate_config(config)
        self.updater = ConsistentUpdater(self.config)
        self.replay = FiveAxisReplay(capacity=self.config['learning']['replay_capacity'])
        seed = self.config['learning']['seed']
        self.warm_rng = np.random.default_rng(seed + 1)
        self.replay_rng = np.random.default_rng(seed + 2)
        self.policy_calls = self.warmup_draws = self.update_attempts = 0
        self.history = []; self.active_episode = False

    def collect(self, session, case, *, seed=None, max_cycles=16000,
                deterministic=False, warmup=False):
        if self.active_episode or self.updater.failed:
            raise RuntimeError('Healthy idle trainer required')
        self.active_episode = True
        before_calls, before_draws = self.policy_calls, self.warmup_draws
        try:
            raw = collect_episode(session, case, seed=seed, max_cycles=max_cycles,
                policy=lambda observation: self.action(observation,
                    deterministic=deterministic, warmup=warmup))
            raw.update(policy_calls=self.policy_calls - before_calls,
                       warmup_draws=self.warmup_draws - before_draws)
            return raw
        except CollectionError as exc:
            exc.archive.update(policy_calls=self.policy_calls - before_calls,
                               warmup_draws=self.warmup_draws - before_draws)
            raise
        finally:
            self.active_episode = False

    def state_dict(self):
        if (self.active_episode or self.updater.failed
                or self.update_attempts != self.updater.counts['critic']):
            raise RuntimeError('Healthy complete checkpoint boundary required')
        return dict(version=STATE_VERSION, learning_version=VERSION,
            numerical_kernel_version=NUMERICAL_KERNEL_VERSION,
            execution_contract=execution_contract(), config=deepcopy(self.config),
            updater=self.updater._snapshot(), replay=self.replay.state_dict(),
            warm_rng=deepcopy(self.warm_rng.bit_generator.state),
            replay_rng=deepcopy(self.replay_rng.bit_generator.state),
            policy_calls=self.policy_calls, warmup_draws=self.warmup_draws,
            update_attempts=self.update_attempts, history=deepcopy(self.history))

    def load_state_dict(self, state):
        if (self.active_episode or not isinstance(state, dict) or set(state) != _STATE_FIELDS
                or state['version'] != STATE_VERSION or state['learning_version'] != VERSION
                or state['numerical_kernel_version'] != NUMERICAL_KERNEL_VERSION
                or not _same(state['execution_contract'], execution_contract())
                or not _same(state['config'], self.config)):
            raise ValueError('Complete matching repaired G1 SAC state required; old states are incompatible')
        validate_config(state['config'])
        # First require the new external contract, then use the frozen validator
        # solely for tensor/Adam/RNG/replay/history invariants. No old disk state
        # is accepted or promoted into this domain.
        numerical = _numerical_config(self.config)
        kernel_state = {key: state[key] for key in _KERNEL_STATE_FIELDS}
        kernel_state.update(version=NUMERICAL_KERNEL_VERSION, config=numerical)
        checked = FiveAxisTrainer(numerical)
        checked.load_state_dict(kernel_state)
        candidate = Trainer(self.config)
        candidate.updater._restore(checked.updater._snapshot())
        candidate.updater._finite_state()
        for name in ('replay', 'warm_rng', 'replay_rng', 'policy_calls',
                     'warmup_draws', 'update_attempts', 'history'):
            setattr(candidate, name, getattr(checked, name))
        self.__dict__.update(candidate.__dict__)


ConsistentTrainer = Trainer


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def save_checkpoint(trainer, path):
    """Write a new directory atomically, with execution and config byte pins."""
    if type(trainer) is not Trainer:
        raise TypeError('New-domain Trainer required')
    config = validate_config(trainer.config)
    state = trainer.state_dict()
    path = Path(path).resolve()
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(path.name + '.stage-' + uuid.uuid4().hex)
    staging.mkdir()
    with (staging / 'state.pt').open('xb') as handle:
        torch.save(state, handle); handle.flush(); os.fsync(handle.fileno())
    manifest = dict(version=CHECKPOINT_VERSION, state_version=STATE_VERSION,
        config_sha256=contract_digest(config),
        execution_contract_sha256=contract_digest(execution_contract()),
        state_sha256=_sha((staging / 'state.pt').read_bytes()))
    encoded = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode('utf-8')
    with (staging / 'manifest.json').open('xb') as handle:
        handle.write(encoded); handle.flush(); os.fsync(handle.fileno())
    os.rename(staging, path)
    return _sha(encoded)


def load_checkpoint(path, *, expected_digest, config):
    config = validate_config(config)
    path = Path(path)
    encoded = (path / 'manifest.json').read_bytes()
    if _sha(encoded) != expected_digest:
        raise ValueError('Checkpoint manifest digest differs')
    manifest = json.loads(encoded)
    expected = dict(version=CHECKPOINT_VERSION, state_version=STATE_VERSION,
        config_sha256=contract_digest(config),
        execution_contract_sha256=contract_digest(execution_contract()))
    if (not isinstance(manifest, dict) or set(manifest) != set(expected) | {'state_sha256'}
            or any(manifest[key] != value for key, value in expected.items())):
        raise ValueError('Checkpoint learning/execution contract differs')
    payload = (path / 'state.pt').read_bytes()
    if _sha(payload) != manifest['state_sha256']:
        raise ValueError('Checkpoint payload digest differs')
    state = torch.load(io.BytesIO(payload), map_location='cpu', weights_only=True)
    trainer = Trainer(config)
    trainer.load_state_dict(state)
    return trainer
