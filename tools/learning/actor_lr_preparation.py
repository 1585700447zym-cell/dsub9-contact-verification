"""Versioned A/B preparation only. No training qualification or execution budget."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from .admission import canonical
from .sac_update import SACUpdater

ROOT = Path(__file__).resolve().parents[2]
PARENT_CONFIG = ROOT / 'deliverables/learning_chain/b2_atomic_repaired_cycle_20260929/config.json'
PARENT_CONFIG_PIN = '18b43f1c27e7a5c33a26ae2127efbf4a48dd5da18cf4bbb3b7fa6d0e60a2b85b'


def preparation_config(branch):
    if branch not in ('A', 'B'):
        raise ValueError('Registered A or B branch required')
    data = PARENT_CONFIG.read_bytes()
    if hashlib.sha256(data).hexdigest() != PARENT_CONFIG_PIN:
        raise ValueError('Parent config bytes changed')
    config = deepcopy(json.loads(data))
    config['version'] = 'actor_lr_preparation_v1'
    config['learning']['actor_learning_rate'] = 3e-4 if branch == 'A' else 3e-5
    config['execution'].update(preparation_only=True, authorized_dynamic_starts=0,
        authorized_optimizer_calls=0, authorized_model_forwards=0)
    config['comparison'] = dict(branch=branch, parent_config_sha256=PARENT_CONFIG_PIN,
        data_source='train_00_through_train_03_only', start='rebuild_four_warmup_zero_updates',
        a_reproduction_required=True, runnable=False)
    return config


def validate_preparation_config(config):
    if not isinstance(config, dict):
        raise ValueError('Preparation config required')
    branch = config.get('comparison', {}).get('branch') if isinstance(config.get('comparison'), dict) else None
    if canonical(config) != canonical(preparation_config(branch)):
        raise ValueError('Unregistered actor learning rate preparation config')


def checkpoint_binding(config, source_manifest_sha256):
    """Preparation identity for future checkpoint integration, not a load permit."""
    validate_preparation_config(config)
    if (not isinstance(source_manifest_sha256, str) or
            re.fullmatch('[0-9a-f]{64}', source_manifest_sha256) is None):
        raise ValueError('Pinned source manifest required')
    return dict(version='actor_lr_preparation_binding_v1', branch=config['comparison']['branch'],
        config_sha256=hashlib.sha256(canonical(config).encode('utf-8')).hexdigest(),
        parent_config_sha256=PARENT_CONFIG_PIN, source_manifest_sha256=source_manifest_sha256)


def validate_checkpoint_binding(binding, config, source_manifest_sha256):
    if canonical(binding) != canonical(checkpoint_binding(config, source_manifest_sha256)):
        raise ValueError('Checkpoint branch or source binding differs')


class PreparationUpdater(SACUpdater):
    config_validator = staticmethod(validate_preparation_config)

    def _blocked(self, *args, **kwargs):
        raise RuntimeError('actor learning rate preparation has no model execution authority')

    predict = targets = _targets = update = _blocked


class PreparationAdmission:
    def verify(self, case=None):
        raise ValueError('actor learning rate preparation has no execution admission')
