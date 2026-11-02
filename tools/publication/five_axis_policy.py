"""Read the published F4000 artifact without replay or optimizer restoration.

CLI verification reads bytes only. load_policy is an explicit library call;
neither import nor CLI runs inference, physics, or an optimizer.
"""
import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FOLDER = ROOT / 'checkpoints/five_axis_F4000'


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def tensor_digest(state):
    """Same named-tensor digest as the original frozen-policy recorder."""
    digest = hashlib.sha256()
    for name, value in sorted(state.items()):
        digest.update(name.encode())
        digest.update(str(value.dtype).encode())
        digest.update(value.detach().cpu().numpy().tobytes())
    return digest.hexdigest()


def verify_artifact(folder=DEFAULT_FOLDER):
    """Verify metadata and bytes without importing torch or constructing a model."""
    folder = Path(folder)
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    if (manifest['artifact_version'] != 'five_axis_policy_only_v1'
            or manifest['updates'] != 4000 or manifest['resumable_training'] is not False):
        raise ValueError('Expected the published F4000 policy-only artifact')
    for name in ('weights.pt', 'config.json'):
        if _sha((folder / name).read_bytes()) != manifest['files'][name]['sha256']:
            raise ValueError('Published artifact digest differs: ' + name)
    return manifest


def load_weights(folder=DEFAULT_FOLDER):
    """Load tensors only; this does not restore or run a trainer."""
    import torch
    folder = Path(folder)
    manifest = verify_artifact(folder)
    state = torch.load(folder / 'weights.pt', map_location='cpu', weights_only=True)
    if set(state) != {'policy', 'log_alpha'}:
        raise ValueError('Unexpected published weights layout')
    if tensor_digest(state['policy']) != manifest['source_policy_sha256']:
        raise ValueError('Published parameters differ from frozen F4000')
    expected = manifest['tensors']
    if set(state['policy']) != set(expected):
        raise ValueError('Published tensor keys differ')
    for name, value in state['policy'].items():
        if list(value.shape) != expected[name]['shape'] or str(value.dtype) != expected[name]['dtype']:
            raise ValueError('Published tensor shape or dtype differs: ' + name)
    return state


def load_policy(folder=DEFAULT_FOLDER):
    """Explicitly construct the existing SB3 SAC policy and load saved parameters.

    Caller supplies observations and stage permission handling; this function
    does not run a forward pass or grant permission for a new physical episode.
    """
    import numpy as np
    import torch
    from gymnasium import spaces
    from stable_baselines3.sac.policies import SACPolicy
    folder = Path(folder)
    state = load_weights(folder)
    config = json.loads((folder / 'config.json').read_text(encoding='utf-8'))
    policy = SACPolicy(
        spaces.Box(-10., 10., shape=(config['width'],), dtype=np.float32),
        spaces.Box(-1., 1., shape=(config['action_dim'],), dtype=np.float32),
        lambda _: config['learning']['learning_rate'],
        net_arch=config['learning']['network'], activation_fn=torch.nn.ReLU)
    policy.load_state_dict(state['policy'], strict=True)
    policy.set_training_mode(False)
    return policy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder', type=Path, default=DEFAULT_FOLDER)
    args = parser.parse_args()
    manifest = verify_artifact(args.folder)
    print(json.dumps(dict(verified=True, updates=manifest['updates'],
                         source_policy_sha256=manifest['source_policy_sha256'],
                         inference_calls=0, physics_initializations=0), ensure_ascii=False))


if __name__ == '__main__':
    main()
