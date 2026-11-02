"""Pinned, atomic five-axis component checkpoints; no mid-physics resume."""
from pathlib import Path
import hashlib
import io
import json
import os
import uuid
import torch
from .five_axis_contract import VERSION, validate_config


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def save_checkpoint(trainer, path):
    path = Path(path).resolve()
    if path.exists(): raise FileExistsError(path)
    state = trainer.state_dict()
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(path.name + '.stage-' + uuid.uuid4().hex)
    staging.mkdir()
    payload = staging / 'state.pt'
    with payload.open('xb') as handle:
        torch.save(state, handle); handle.flush(); os.fsync(handle.fileno())
    manifest = json.dumps(dict(version=VERSION, state_sha256=_sha(payload.read_bytes())), sort_keys=True).encode('utf-8')
    with (staging / 'manifest.json').open('xb') as handle:
        handle.write(manifest); handle.flush(); os.fsync(handle.fileno())
    os.rename(staging, path)
    return _sha(manifest)


def load_checkpoint(path, *, expected_digest, config):
    validate_config(config)
    path = Path(path)
    encoded = (path / 'manifest.json').read_bytes()
    if _sha(encoded) != expected_digest: raise ValueError('Checkpoint manifest digest differs')
    manifest = json.loads(encoded)
    if set(manifest) != {'version', 'state_sha256'} or manifest['version'] != VERSION:
        raise ValueError('Wrong checkpoint version')
    payload = (path / 'state.pt').read_bytes()
    if _sha(payload) != manifest['state_sha256']: raise ValueError('Checkpoint payload digest differs')
    state = torch.load(io.BytesIO(payload), map_location='cpu', weights_only=True)
    from .five_axis_training import FiveAxisTrainer
    trainer = FiveAxisTrainer(config)
    trainer.load_state_dict(state)
    return trainer
