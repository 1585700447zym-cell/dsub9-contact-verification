"""Read existing bytes only; no learning/simulation imports or executable training."""
import gzip
import ast
import hashlib
import importlib.abc
import json
import math
from pathlib import Path
import statistics
import sys
from collections import Counter


class NoRuntime(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in ('torch', 'mujoco', 'stable_baselines3', 'tools'):
            raise RuntimeError('Archive-only review forbids runtime imports')


sys.meta_path.insert(0, NoRuntime())
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OLD = ROOT / 'deliverables/learning_chain/b2_atomic_repaired_cycle_20260929'
REVIEW = OLD.parent / 'b2_force_mechanism_review_20260929'


def read(p):
    return json.loads(p.read_text(encoding='utf-8'))


def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


sealed = read(OLD / 'sealed_files.json')
inputs = {}


def checked(p):
    key = p.relative_to(ROOT).as_posix()
    actual = sha(p)
    assert actual == sealed[key], key
    inputs[key] = actual
    return p.read_bytes()


def action_stats(rows):
    if not rows:
        return None
    # Only adjacent active rows count as consecutive policy actions.
    pairs = [(a, b) for a, b in zip(rows, rows[1:])
             if abs(b['trace_row']['time_s'] - a['trace_row']['time_s'] - b['dt']) < 1e-7]
    result = []
    for j in range(4):
        vals = [r['action'][j] for r in rows]
        signed = sum(r['action'][j] * r['dt'] for r in rows)
        absolute = sum(abs(r['action'][j]) * r['dt'] for r in rows)
        result.append(dict(mean=statistics.mean(vals), mean_abs=statistics.mean(map(abs, vals)),
            fraction_abs_gt_095=sum(abs(v) > .95 for v in vals) / len(vals),
            same_sign_adjacent_fraction=(sum(a['action'][j] * b['action'][j] > 0 for a, b in pairs)
                                         / len(pairs) if pairs else None),
            signed_integral_normalized_seconds=signed,
            coherence=abs(signed) / absolute if absolute else 0.))
    return dict(rows=len(rows), duration_s=sum(r['dt'] for r in rows), axes=result)


ledger = json.loads(checked(OLD / 'run/ledger.json'))
updates = json.loads(checked(OLD / 'run/training/updates.json'))
assert ledger['dynamic_starts'] == 13 and len(updates) == 2500
episodes = []
for entry in ledger['attempts']:
    folder = 'initial/episodes' if entry['stage'] == 'initial' else 'training_episodes'
    raw = json.loads(gzip.decompress(checked(OLD / 'run' / folder / entry['id'] / 'episode.json.gz')))
    rows = raw['transitions']
    active = [r for r in rows if r['action_active']]
    boundary = max(i for i, r in enumerate(rows) if r['action_active'])
    tail = [r for r in active if raw['stop_time'] - .5 <= r['trace_row']['time_s'] <= raw['stop_time'] + 1e-8]
    label = 0.
    for r in reversed(rows[boundary:]):
        label = r['reward'] + r['discount'] * label
    peak = max(.025 * math.sqrt(max(0., -r['reward_terms']['force'] / (.2 * r['dt']))) for r in rows)
    reward_sums = {key: sum(r['reward_terms'][key] for r in rows) for key in rows[0]['reward_terms']}
    assert math.isclose(reward_sums['total'], sum(r['reward'] for r in rows), abs_tol=1e-8)
    episodes.append(dict(id=entry['id'], stage=entry['stage'], case=raw['case'],
        sampling_mode=raw.get('sampling_mode', 'initial_evaluation_mode_not_in_archive'), updates_at_start=raw['optimizer_steps_start'],
        outcome=entry['result']['task_outcome'], simulation_valid=entry['result']['simulation_valid'],
        physical_stopped=entry['result']['physical_stopped'], peak_from_reward_N=peak,
        force_margin_pct=100*(1-peak/.025), active=action_stats(active), last_half_second=action_stats(tail),
        observation_clip_entries=sum(abs(v) >= 10 for r in rows for v in r['observation']),
        observation_clip_by_index=dict(Counter(i for r in rows for i,v in enumerate(r['observation']) if abs(v) >= 10)),
        active_observation_clip_by_index=dict(Counter(i for r in active for i,v in enumerate(r['observation']) if abs(v) >= 10)),
        observation_entries=120*len(rows), reward_sums=reward_sums, exact_boundary_label=label,
        request_integral_units='Normalized action seconds; NOT physical displacement or executed residual'))

blocks = []
for start in range(0, 2500, 500):
    block = updates[start:start+500]
    blocks.append(dict(first_batch=start+1, last_batch=start+500, audited_total=block[0]['audited_total'],
        episodes=block[0]['episodes'],
        means={k: statistics.mean(r[k] for r in block) for k in
               ('critic_loss', 'actor_loss', 'entropy_abs_mean', 'reward_abs_mean', 'exact_target_rows', 'active_rows')},
        alpha_last=block[-1]['alpha_after'],
        target_abs_max=max(r['target_abs_max'] for r in block)))

probe = read(REVIEW / 'critic_probe/results.json')
assert (probe['states'], probe['state_action_pairs']) == (1747, 20968)
boundary = next(r for r in probe['checkpoints'][-1]['scores'] if r['episode'] == 'train_08' and r['boundary'])
assert not boundary['in_checkpoint_replay']
assert math.isclose(boundary['exact_tail_label'], episodes[-1]['exact_boundary_label'], abs_tol=1e-10)
review_hashes = read(REVIEW / 'verification.json')['artifacts_sha256']
for relative, expected in review_hashes.items():
    assert sha(REVIEW / relative) == expected, relative
    inputs[(REVIEW / relative).relative_to(ROOT).as_posix()] = expected
for cp in probe['checkpoints']:
    p = OLD / 'run' / cp['checkpoint']['path']
    assert sha(p / 'manifest.json') == cp['checkpoint']['sha256']
    assert sha(p / 'state.pt') == cp['state_file_sha256'] == read(p / 'manifest.json')['state_sha256']
    assert cp['complete_state_unchanged'] and cp['process_rng_unchanged']

source_hashes = {p.relative_to(ROOT).as_posix(): sha(p) for folder in ('tools', 'tests', 'docs/stage_b')
                 for p in (ROOT / folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts}
before = HERE / 'source_before.json'
if before.exists():
    assert read(before) == source_hashes, 'Protected source/test/contract changed during review'
else:
    before.write_text(json.dumps(source_hashes, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
tree = ast.parse((ROOT / 'tools/learning/observation.py').read_text(encoding='utf-8'))
width_expr = next(n.value for n in tree.body if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == 'VECTOR_WIDTHS' for t in n.targets))
widths = {k.arg: ast.literal_eval(k.value) for k in width_expr.keywords}
capture = next(n for c in tree.body if isinstance(c, ast.ClassDef) and c.name == 'ObservationBuilder'
               for n in c.body if isinstance(n, ast.FunctionDef) and n.name == 'capture')
schema = []
for node in capture.body:
    if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
        continue
    call = node.value
    if isinstance(call.func, ast.Name) and call.func.id in ('add', 'onehot', 'timer'):
        name = ast.literal_eval(call.args[0])
        if call.func.id == 'timer':
            schema.extend([name+'_elapsed_s', name+'_valid'])
        else:
            schema.extend([name]*widths.get(name, 1))
assert len(schema) == 120
clipped_indices = {i for e in episodes for i in e['observation_clip_by_index']}
clipped_fields = {str(i): schema[i] for i in sorted(clipped_indices)}
assert not any(m.split('.')[0] in ('torch', 'mujoco', 'stable_baselines3', 'tools') for m in sys.modules)
result = dict(date='2026-09-30', scope='archive_only', physics=0, actor_forwards=0,
    critic_forwards=0, optimizer_updates=0, episodes=episodes, update_blocks=blocks,
    dangerous_boundary=boundary, verified_inputs_sha256=inputs, verified_checkpoint_count=4,
    observation_clipped_fields_from_source=clipped_fields,
    protected_source_count=len(source_hashes), limitations=[
        'No causal physical counterfactual, no fresh policy evaluation, no new model computation.',
        'Adjacent sign persistence is not evidence of policy quality or causation.',
        'No clipping does not establish observation sufficiency or Markov state.',
        'Small archive sample and changing policies do not yield an independent success-rate comparison.'])
(HERE / 'archive_review.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
for e in episodes:
    print(e['id'], e['outcome'], 'mean', [round(a['mean'],3) for a in e['active']['axes']],
          'same_sign', [round(a['same_sign_adjacent_fraction'],3) for a in e['active']['axes']],
          'coherence', [round(a['coherence'],3) for a in e['active']['axes']],
          'clip', e['observation_clip_entries'])
print(json.dumps(dict(update_blocks=blocks, checked_inputs=len(inputs), checkpoints=4,
                     physics=0, model_forwards=0, updates=0), indent=2))
