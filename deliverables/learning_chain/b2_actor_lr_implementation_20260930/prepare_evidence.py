"""Build preparation records from archive bytes; never execute a learning cycle."""
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OLD = ROOT / 'deliverables/learning_chain/b2_atomic_repaired_cycle_20260929'
sys.path.insert(0, str(ROOT))
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
os.environ['MPLCONFIGDIR'] = str(ROOT / 'tmp/learning_mpl_cache')
from tools.learning.runtime import verify_runtime
verify_runtime(ROOT / 'tmp/mujoco_3_13_probe')
import torch
import mujoco

calls = dict(model_forward=0, optimizer_step=0, physics=0)


def forbidden(kind):
    def fail(*args, **kwargs):
        calls[kind] += 1
        raise AssertionError('Forbidden during evidence preparation: ' + kind)
    return fail


torch.nn.Module._call_impl = forbidden('model_forward')
torch.optim.Adam.step = forbidden('optimizer_step')
for name in ('mj_forward', 'mj_step', 'mj_step1', 'mj_step2', 'mj_resetData', 'mj_resetDataKeyframe'):
    setattr(mujoco, name, forbidden('physics'))
from tools.learning.actor_lr_preparation import preparation_config, validate_preparation_config, checkpoint_binding
from tools.learning.policy_distribution_diagnostics import select_state_indices


def read(p):
    return json.loads(p.read_text(encoding='utf-8'))


def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def write(name, obj):
    data = (json.dumps(obj, ensure_ascii=False, allow_nan=False, indent=2)+'\n').encode('utf-8')
    p = HERE / name
    if p.exists() and p.read_bytes() != data:
        raise ValueError('Preparation artifact changed; use a new version: ' + name)
    if not p.exists():
        p.write_bytes(data)


before = read(HERE / 'protected_before.json')
snapshots = read(HERE / 'parent_source_snapshots.json')
changes = {rel: (expected, sha(ROOT / rel)) for rel,expected in before.items() if sha(ROOT / rel) != expected}
assert set(changes) == {'tools/learning/sac_update.py'}
for rel,expected in before.items():
    assert sha(ROOT / snapshots.get(rel, rel)) == expected, rel
old_candidate = read(OLD / 'candidate.json')
for rel,expected in old_candidate['source_sha256'].items():
    assert sha(ROOT / snapshots.get(rel, rel)) == expected, rel
sealed = read(OLD / 'sealed_files.json')
for rel,expected in sealed.items():
    assert sha(ROOT / rel) == expected, rel

sources = {p.relative_to(ROOT).as_posix(): sha(p) for folder in ('tools', 'tests', 'docs/stage_b')
           for p in (ROOT / folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts}
write('source_sha256.json', sources)
pin = sha(HERE / 'source_sha256.json')
for branch in ('A', 'B'):
    config = preparation_config(branch)
    validate_preparation_config(config)
    write('config_' + branch + '.json', config)
    write('binding_' + branch + '.json', checkpoint_binding(config, pin))

selected = []
archives = []
for i in range(4):
    path = OLD / 'run/training_episodes' / f'train_{i:02d}' / 'episode.json.gz'
    archive_pin = sha(path)
    assert archive_pin == sealed[path.relative_to(ROOT).as_posix()]
    raw = json.loads(gzip.decompress(path.read_bytes()))
    assert raw['optimizer_steps'] == raw['optimizer_steps_start'] == 0
    assert raw['sampling_mode'] == 'uniform_warmup'
    assert raw['outcome']['simulation_valid'] and raw['outcome']['physical_stopped'] and raw['outcome']['valid_for_learning']
    indices = select_state_indices(raw['transitions'], count=64)
    for index in indices:
        observation = raw['transitions'][index]['observation']
        assert len(observation) == 120 and all(type(v) in (int,float) and math.isfinite(v) and abs(v) <= 10 for v in observation)
        selected.append(dict(episode=raw['episode_id'], index=index, observation=observation))
    archives.append(dict(path=path.relative_to(ROOT).as_posix(), sha256=archive_pin,
        rows=len(raw['transitions']), state_indices=indices))
assert len(selected) == 256 and sum(a['rows'] for a in archives) == 22766
write('diagnostic_states.json', dict(kind='fixed_development_states_no_forward', states=selected, archives=archives))
checkpoint = OLD / 'run/initial_checkpoint'
assert sha(checkpoint / 'state.pt') == read(checkpoint / 'manifest.json')['state_sha256']
write('rebuild_requirements.json', dict(reconstructed=False, a_reproduced=False,
    initial_checkpoint_path=checkpoint.relative_to(ROOT).as_posix(),
    manifest_sha256=sha(checkpoint/'manifest.json'), state_sha256=sha(checkpoint/'state.pt'),
    source_archives=archives, pool_rows=22766, gradient_batches_at_start=0,
    note='No checkpoint was loaded. Full replay/boundary/RNG reconstruction and A reproduction await authorized computation.'))
write('proposed_compute.json', dict(approved=False, runnable=False, automatic_tracking=False,
    formal_batches=dict(A=500, B=500, total=1000), physical_starts=dict(A=4, B=4, total=8),
    synthetic_transaction_attempts=16, extra_test_state_forwards=128,
    diagnostic_actor_state_forwards=768, diagnostic_critic_state_forwards=0,
    online_training_collection=0, new_warmup_physics=0, independent_test=0,
    old_unused_dynamic=19, old_unused_batches=2000, old_unused_budget_consumed=0,
    fail_on_a_reproduction_mismatch=True, stop_on_any_evaluation_guard=True, automatic_retry=False,
    note='Each optimizer transaction includes its required network computations; physical evaluation actor calls belong to its dynamic budget. No proposed budget is authorized by the repair request.'))
assert not any(calls.values())
write('preparation_receipt.json', dict(status='artifacts_prepared_no_execution',
    inherited_source_files=len(old_candidate['source_sha256']), protected_original_files=len(before),
    sealed_old_files=len(sealed), changed_inherited_sources=list(changes), current_sources=len(sources),
    source_manifest_sha256=pin, diagnostic_states=256, replay_rows_to_rebuild=22766,
    forbidden_call_counts=calls, qualification_issued=False, training_launched=False))
print(json.dumps(read(HERE/'preparation_receipt.json'), ensure_ascii=True, indent=2))
