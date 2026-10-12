"""Reconstruct and cross-check the common start with every execution blocked."""
from copy import deepcopy
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OLD = ROOT / 'deliverables/learning_chain/b2_atomic_repaired_cycle_20260929'
sys.path.insert(0, str(ROOT))
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
os.environ['MPLCONFIGDIR'] = str(ROOT / 'tmp/learning_mpl_cache')


def read(p):
    return json.loads(p.read_text(encoding='utf-8'))


def sha(p):
    with p.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


from tools.learning.runtime import select_runtime, active_package, verify_runtime
repaired = ROOT / 'deliverables/learning_chain/b2_repaired_cycle_v2_20260928'
select_runtime(repaired / 'runtime.json', expected_digest=read(repaired / 'admission.json')['runtime_record_sha256'])
verify_runtime(active_package())
import torch
import mujoco
import numpy as np

calls = dict(model_forward=0, optimizer_step=0, physics=0)


def forbidden(kind):
    def fail(*args, **kwargs):
        calls[kind] += 1
        raise AssertionError('Forbidden during origin reconstruction: ' + kind)
    return fail


torch.nn.Module._call_impl = forbidden('model_forward')
torch.optim.Adam.step = forbidden('optimizer_step')
for name in ('mj_forward', 'mj_step', 'mj_step1', 'mj_step2', 'mj_resetData', 'mj_resetDataKeyframe'):
    setattr(mujoco, name, forbidden('physics'))
from tools.learning.actor_lr_origin import read_pinned_state, rebuild_origin, fork_origin, draw_plan
from tools.learning.actor_lr_preparation import preparation_config
from tools.learning.sac_checkpoint import _same
from tools.learning.admission import canonical
from tools.validation.verify_residual_interface import qualified_runtime

# Never re-run old qualification scripts after changing their source bindings.
before = read(HERE / 'protected_before.json')
for rel, pin in before.items():
    assert sha(ROOT / rel) == pin, rel
for rel, pin in read(HERE / 'parent_files.json').items():
    assert sha(ROOT / rel) == pin, rel
sealed = read(OLD / 'sealed_files.json')
for rel, pin in sealed.items():
    assert sha(ROOT / rel) == pin, rel
candidate_pin = sha(OLD / 'candidate.json')
assert candidate_pin == 'ab2fefe0ae4eb6850d5aae768dff7a7c952302e3893f68721fb41a4adf3de379'
runtime = qualified_runtime(active_package())
assert _same(runtime, read(OLD / 'candidate.json')['runtime'])
inputs = {}


def checkpoint(relative):
    path = OLD / 'run' / relative
    manifest = path / 'manifest.json'
    assert sha(manifest) == sealed[manifest.relative_to(ROOT).as_posix()]
    state_file = path / 'state.pt'
    assert sha(state_file) == sealed[state_file.relative_to(ROOT).as_posix()]
    for p in (manifest, state_file):
        inputs[p.relative_to(ROOT).as_posix()] = sha(p)
    return read_pinned_state(path, sha(manifest))


initial = checkpoint('initial_checkpoint')
prefix = checkpoint('training/checkpoints/train_02')
historical = checkpoint('training/checkpoints/train_03')
pairs = []
for i in range(4):
    path = OLD / 'run/training_episodes' / f'train_{i:02d}'
    for name in ('status.json', 'episode.json.gz'):
        p = path / name
        inputs[p.relative_to(ROOT).as_posix()] = sha(p)
        assert sha(p) == sealed[p.relative_to(ROOT).as_posix()]
    pairs.append((read(path / 'status.json'), (path / 'episode.json.gz').read_bytes()))
global_rng = torch.get_rng_state().clone()
origin, index = rebuild_origin(initial, pairs, candidate_pin)
assert torch.equal(global_rng, torch.get_rng_state()), 'Global torch RNG changed'
assert _same(initial['updater'], prefix['updater']), 'Three-warmup network/Adam/torch RNG changed'
assert _same(origin['binding'], prefix['binding']) == _same(origin['binding'], historical['binding']) is True
for key in ('archives', 'attempts'):
    value = {k:v for k,v in origin[key].items() if k != 'train_03'} if key == 'archives' else origin[key][:3]
    assert _same(value, prefix[key]), 'Three-warmup archive/receipt cross-check: ' + key
assert _same(origin['replay']['episodes'][:3], prefix['replay']['episodes'])
assert prefix['replay']['capacity'] == 156000 and prefix['replay']['size'] == 16887
assert prefix['replay']['seen'] == ['train_00', 'train_01', 'train_02']
assert prefix['sampler_count'] == 3 and prefix['update_attempts'] == 0 and prefix['history'] == []
assert prefix['budget'] == dict(total=16887, completed=0,
    receipts={k:v for k,v in origin['budget']['receipts'].items() if k != 'train_03'})
g = np.random.Generator(np.random.PCG64(np.random.SeedSequence([2026092716,1])))
g.bit_generator.advance(4*16887)
assert prefix['rng']['warmup'] == g.bit_generator.state
for key in ('replay','boundary'):
    assert prefix['rng'][key] == origin['rng'][key]
for key in ('archives','attempts','replay','sampler_count'):
    assert _same(origin[key], historical[key]), 'Four-warmup cross-check: ' + key
assert origin['budget']['receipts'] == historical['budget']['receipts']
assert historical['budget']['total'] == 22766 and historical['budget']['completed'] == 500
assert origin['rng']['warmup'] == historical['rng']['warmup']
lengths = [len(arrays['rewards']) for _,arrays in origin['replay']['episodes']]
boundaries = [index.entries[f'train_{i:02d}'][2] for i in range(4)]
plan = draw_plan(lengths, boundaries, {key:origin['rng'][key] for key in ('replay','boundary')})
assert len(historical['history']) == 500
for row, old_row in zip(plan['batches'], historical['history']):
    assert row['critic_indices'][-16:] == old_row['boundary_indices']
    assert old_row['critic_batches'] == row['batch'] and old_row['episodes'] == 4
    assert old_row['audited_total'] == 22766 and old_row['credit_remaining'] == 500-row['batch']
assert plan['final_rng'] == {key:historical['rng'][key] for key in ('replay','boundary')}
assert not any(calls.values())
sources = {p.relative_to(ROOT).as_posix():sha(p) for folder in ('tools','tests','docs/stage_b')
    for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts}
name = sys.argv[1] if len(sys.argv) > 1 else 'origin'
if name not in ('origin', 'origin_v2'):
    raise ValueError('Registered preparation output required')
output = HERE / name
output.mkdir(exist_ok=False)


def json_file(name, value):
    p = output / name
    with p.open('xb') as stream:
        stream.write((json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2)+'\n').encode('utf-8'))


json_file('source_sha256.json', sources)
source_pin = sha(output / 'source_sha256.json')
# Keep one common state. Forks below only test equality/isolation and are not
# persisted as falsely admitted checkpoints. Future execution reloads the pin.
a, b = fork_origin(origin, 'A', source_pin), fork_origin(origin, 'B', source_pin)
normalized = deepcopy(b)
normalized['comparison_binding'] = deepcopy(a['comparison_binding'])
normalized['updater']['actor']['param_groups'][0]['lr'] = 3e-4
assert _same(a, normalized)
for key in a['updater']['policy']:
    assert a['updater']['policy'][key].untyped_storage().data_ptr() != b['updater']['policy'][key].untyped_storage().data_ptr()
for (_,arrays_a),(_,arrays_b) in zip(a['replay']['episodes'],b['replay']['episodes']):
    for key in arrays_a:
        assert arrays_a[key].untyped_storage().data_ptr() != arrays_b[key].untyped_storage().data_ptr()
json_file('branch_binding_A.json', a['comparison_binding'])
json_file('branch_binding_B.json', b['comparison_binding'])
json_file('config_A.json', preparation_config('A'))
json_file('config_B.json', preparation_config('B'))
origin['boundary_index'] = {key:dict(targets=torch.tensor(targets), mask=torch.tensor(mask), boundary=boundary)
    for key,(targets,mask,boundary) in index.entries.items()}
with (output / 'state.pt').open('xb') as stream:
    torch.save(origin,stream)
payload = (output / 'state.pt').read_bytes()
restored = torch.load(io.BytesIO(payload),map_location='cpu',weights_only=True)
assert _same(origin,restored), 'Reconstructed state roundtrip differs'
compressed_plan = gzip.compress(canonical(plan).encode('utf-8'),mtime=0)
with (output / 'draw_plan.json.gz').open('xb') as stream:
    stream.write(compressed_plan)
json_file('manifest.json', dict(version='actor_lr_origin_manifest_v1', state_sha256=sha(output/'state.pt'),
    draw_plan_sha256=sha(output/'draw_plan.json.gz'), source_manifest_sha256=source_pin,
    parent_candidate_sha256=candidate_pin, archived_inputs_sha256=inputs,
    replay_rows=22766, warmup_episodes=4, formal_updates=0, earned_credit=500,
    origin_is_not_execution_checkpoint=True, qualification_issued=False, user_execution_authorized=False))
json_file('assessment.json', dict(status='common_origin_reconstructed_no_execution',
    prefix_3_warmup_exact=True, four_warmup_data_and_rng_exact=True,
    warmup_requests_exact=True, empty_initial_weights_adam_temperature_torch_rng_exact=True,
    draws_500_boundary_history_and_final_rng_exact=True, a_500_learning_reproduced=False,
    fork_only_actor_rate_and_identity_differ=True, fork_mutable_storage_disjoint=True,
    save_load_exact=True, global_torch_rng_unchanged=True, runtime_exact=runtime,
    model_forward_calls=calls['model_forward'], optimizer_step_calls=calls['optimizer_step'], physics_calls=calls['physics'],
    qualification_issued=False, training_launched=False, policy_effect_validated=False))
print(json.dumps(dict(status='common_origin_reconstructed', rows=22766, warmup_requests=22766,
    frozen_batches=500, source_files=len(sources), calls=calls, a_learning_reproduced=False),ensure_ascii=True))
