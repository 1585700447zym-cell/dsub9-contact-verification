"""Read pinned archived checkpoint structure; no model construction/execution."""
import hashlib
import io
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
os.environ['MPLCONFIGDIR'] = str(ROOT / 'tmp/learning_mpl_cache')
from tools.learning.runtime import verify_runtime
verify_runtime(ROOT / 'tmp/mujoco_3_13_probe')
import torch
import mujoco


def forbidden(*args, **kwargs):
    raise AssertionError('No forwards, optimizer steps or physics in origin inspection')


torch.nn.Module._call_impl = forbidden
torch.optim.Adam.step = forbidden
for name in ('mj_forward', 'mj_step', 'mj_step1', 'mj_step2', 'mj_resetData', 'mj_resetDataKeyframe'):
    setattr(mujoco, name, forbidden)
old = ROOT / 'deliverables/learning_chain/b2_atomic_repaired_cycle_20260929'
for key in ('initial_checkpoint', 'training/checkpoints/train_02', 'training/checkpoints/train_03'):
    path = old / 'run' / key
    manifest = json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
    payload = (path / 'state.pt').read_bytes()
    assert hashlib.sha256(payload).hexdigest() == manifest['state_sha256']
    state = torch.load(io.BytesIO(payload), map_location='cpu', weights_only=True)
    print(json.dumps(dict(checkpoint=key, keys=list(state), version=state['version'],
        counts=state['updater']['counts'], updater_keys=list(state['updater']),
        budget=state['budget'], sampler_count=state['sampler_count'], update_attempts=state['update_attempts'],
        attempts=len(state['attempts']), history=len(state['history']),
        rng=state['rng'], replay_metadata={k:v for k,v in state['replay'].items() if k!='episodes'},
        binding_keys=list(state['binding']), qualification=state['binding']['qualification_sha256'],
        record_keys=list(state['binding']['record'])), ensure_ascii=True))
parent = ROOT / 'deliverables/learning_chain/b2_actor_lr_implementation_20260930'
sources = json.loads((parent / 'source_sha256.json').read_text(encoding='utf-8'))
for rel, pin in sources.items():
    assert hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == pin
(HERE / 'protected_before.json').write_text(json.dumps(sources, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
pins = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in parent.rglob('*') if p.is_file() and not any(s.endswith('_work') for s in p.parts)}
(HERE / 'parent_files.json').write_text(json.dumps(pins, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps(dict(protected_sources=len(sources), parent_artifacts=len(pins))))
