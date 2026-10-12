"""Self-contained, CPU learning checkpoints at audited publication boundaries.

The manifest digest must be supplied out of band. A sibling staging directory
is flushed before its final rename; interrupted staging is never loadable as
the requested checkpoint. This is process-interruption durability, not a claim
of power-loss durability on every filesystem. No MuJoCo state is resumed.
"""
from copy import deepcopy
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import uuid

import numpy as np
import torch

from .admission import canonical, digest, validate_case, validate_config
from .audited_replay import AuditedReplay
from .sac_collection import SACCollection, UpdateBudget, qualified_update_limit
from .sac_update import SACUpdater


def _same(a, b):
    if isinstance(a, torch.Tensor):
        return isinstance(b, torch.Tensor) and a.dtype == b.dtype and a.shape == b.shape and torch.equal(a, b)
    if isinstance(a, dict):
        return isinstance(b, dict) and a.keys() == b.keys() and all(_same(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)):
        return type(a) is type(b) and len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    return type(a) is type(b) and a == b


def _integer(value, minimum=0, maximum=None):
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        raise ValueError('Invalid checkpoint counter')
    return value


def _replay_state(replay):
    return dict(capacity=replay.capacity, size=len(replay), seen=sorted(replay._state.seen),
        episodes=[[key, {k: torch.tensor(v.copy()) for k, v in arrays.items()}]
                  for key, arrays in replay._state.episodes])


def _audit_physics(raw):
    from tools.validation.verify_admitted_collection import validate_outcome
    from tools.validation.native313_matrix_audit import actual_stop_pass
    from tools.validation.run_contact_candidate_stop import physical_tail_pass
    stopped = actual_stop_pass(raw['stop_samples'], raw['events'], raw['stop_time'], raw['audit_end_time_s'], .0002)
    stopped = stopped and physical_tail_pass(raw['stop_samples'], raw['audit_end_time_s'], .0002)
    validate_outcome(raw, stopped=stopped)
    if not stopped: raise ValueError('Checkpoint contains an episode that did not stop')


def capture(chain):
    """Detached complete state. Read only: do not synchronize or consume RNG."""
    c = chain.collector
    if (chain.failed or chain.updater.failed or c.active or c._blocked or c._pending is not None or
            c._status_pending or c.session is not None or getattr(c, 'buffer', None) is not None):
        raise RuntimeError('Checkpoint requires a healthy audited and published episode boundary')
    record = chain.admission.verify()
    archives = {}
    for attempt in c.attempts:
        key = attempt['episode_id']
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', key): raise ValueError('Unsafe episode ID')
        folder = c.output / key
        status = json.loads((folder / 'status.json').read_text(encoding='utf-8'))
        if status != attempt: raise ValueError('Publication receipt not durably committed')
        archives[key] = (folder / 'episode.json.gz').read_bytes()
    version = 'contact_checkpoint_v1' if record.get('capability') == 'contact_four_point_execution' else 'sac_checkpoint_v1'
    return deepcopy(dict(version=version,
        binding=dict(qualification_sha256=chain.admission.expected_digest, record=record),
        updater=chain.updater._snapshot(), replay=_replay_state(chain.replay), archives=archives,
        attempts=c.attempts, history=chain.history,
        budget=dict(total=chain.budget.total, completed=chain.budget.completed, receipts=chain.budget._receipts),
        sampler=dict(count=chain.sampler.count, rng=chain.sampler.rng.bit_generator.state),
        rng=dict(warmup=chain.warmup.rng.bit_generator.state, replay=chain.replay_rng.bit_generator.state)))


def _tensor(value, reference):
    if (not isinstance(value, torch.Tensor) or value.device.type != 'cpu' or value.requires_grad or
            value.shape != reference.shape or value.dtype != reference.dtype or not torch.isfinite(value).all()):
        raise ValueError('Invalid checkpoint tensor type, shape or value')


def _optimizer(saved, optimizer, count):
    template = optimizer.state_dict()
    if saved.keys() != template.keys() or saved['param_groups'] != template['param_groups']:
        raise ValueError('Optimizer configuration changed')
    ids = [p for g in template['param_groups'] for p in g['params']]
    params = [p for g in optimizer.param_groups for p in g['params']]
    expected = set(ids) if count else set()
    if set(saved['state']) != expected: raise ValueError('Missing or extra optimizer moments')
    for identity, parameter in zip(ids, params):
        if not count: continue
        entry = saved['state'][identity]
        if set(entry) != {'step', 'exp_avg', 'exp_avg_sq'}: raise ValueError('Incomplete Adam state')
        _tensor(entry['step'], torch.tensor(0.))
        if entry['step'].item() != count: raise ValueError('Adam step and counter disagree')
        _tensor(entry['exp_avg'], parameter.detach())
        _tensor(entry['exp_avg_sq'], parameter.detach())
        if (entry['exp_avg_sq'] < 0).any(): raise ValueError('Negative second moment')


def _rng(state):
    if not isinstance(state, dict) or state.get('bit_generator') != 'PCG64': raise ValueError('Wrong RNG family')
    result = np.random.Generator(np.random.PCG64())
    result.bit_generator.state = deepcopy(state)
    if result.bit_generator.state != state: raise ValueError('Malformed RNG state')
    return result


def validate_state(state, admission):
    """Build checked components privately, before any destination is created."""
    record = admission.verify()
    from .contact_execution import ContactAdmission, ContactUpdater, ContactBudget, ContactSampler
    from .contact_contract import validate_config as contact_config_validator, validate_case as contact_case_validator, guard_clear
    contact = isinstance(admission, ContactAdmission)
    version = 'contact_checkpoint_v1' if contact else 'sac_checkpoint_v1'
    binding = dict(qualification_sha256=admission.expected_digest, record=record)
    if state.get('version') != version or canonical(state.get('binding')) != canonical(binding):
        raise ValueError('Checkpoint configuration, source, runtime or qualification differs')
    config = record['config']
    (contact_config_validator if contact else validate_config)(config)
    max_updates = qualified_update_limit(admission, record)
    replay, budget = AuditedReplay(capacity=config['learning']['replay_capacity']), (ContactBudget if contact else UpdateBudget)(config)
    attempts = state['attempts']
    ids = [r['episode_id'] for r in attempts]
    if not ids or len(set(ids)) != len(ids) or set(ids) != set(state['archives']):
        raise ValueError('Missing or repeated attempt/archive')
    cumulative = {0}
    previous_steps = 0
    episode_boundaries = []
    expected_sampler = ContactSampler(config) if contact else None
    if contact and not 1 <= len(attempts) <= 6: raise ValueError('Contact attempt budget exceeded')
    for receipt in attempts:
        key = receipt['episode_id']
        if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', key):
            raise ValueError('Unsafe episode ID')
        compressed = state['archives'][key]
        if not isinstance(compressed, bytes) or hashlib.sha256(compressed).hexdigest() != receipt['archive_sha256']:
            raise ValueError('Episode archive digest mismatch')
        raw = json.loads(gzip.decompress(compressed))
        (contact_case_validator if contact else validate_case)(raw['case'])
        if contact:
            if (budget.total >= 20000 or not guard_clear(raw) or raw.get('guard_clear') is not True or
                receipt.get('guard_clear') is not True or raw['case'] != expected_sampler.next_case() or
                not 0 < len(raw['transitions']) <= 13000):
                raise ValueError('Contact checkpoint contains an unqualified attempt')
        for name in ('episode_id', 'case', 'seed', 'qualification_sha256', 'optimizer_steps',
                     'optimizer_steps_start', 'policy_sha256', 'sampling_mode', 'audit_end_time_s'):
            if not _same(raw[name], receipt[name]): raise ValueError(f'Raw receipt mismatch: {name}')
        if (raw['qualification_sha256'] != admission.expected_digest or raw['seed'] != config['sampling']['seed'] or
                raw['fault'] is not None or raw['sampling_mode'] != ('uniform_warmup' if budget.total < 5000 else 'sac_policy')):
            raise ValueError('Invalid raw qualification or sampling mode')
        steps = _integer(raw['optimizer_steps'], previous_steps, max_updates)
        if contact and steps != budget.available: raise ValueError('Contact updates not exhausted before next episode')
        if _integer(raw['optimizer_steps_start']) != steps or steps > budget.available:
            raise ValueError('Updates occurred during the episode or before earning credit')
        episode_boundaries.append((budget.total, steps))
        previous_steps = steps
        _audit_physics(raw)
        for name in ('physical_stopped', 'simulation_valid', 'valid_for_learning', 'task_outcome'):
            if not _same(raw['outcome'][name], receipt[name]): raise ValueError('Outcome and receipt disagree')
        result = replay.publish(key, raw['transitions'], outcome=raw['outcome'], training_admitted=True)
        if (any(type(receipt[k]) is not int or result[k] != receipt[k] for k in result) or
                _integer(receipt['steps'], 1) != len(raw['transitions'])):
            raise ValueError('Replay publication counts disagree')
        if not budget.record(receipt): raise ValueError('Duplicate publication receipt')
        cumulative.add(budget.total)
    if not _same(_replay_state(replay), state['replay']): raise ValueError('Replay does not match audited archives')
    saved = state['updater']; counts = saved['counts']
    if set(counts) != {'actor', 'critic', 'temperature', 'target'}: raise ValueError('Missing update counters')
    for value in counts.values(): _integer(value, 0, max_updates)
    if counts['target'] != counts['critic'] or counts['actor'] != counts['temperature'] or counts['actor'] > counts['critic']:
        raise ValueError('Inconsistent update counters')
    completed = _integer(state['budget']['completed'], 0, max_updates)
    if completed != counts['critic'] or completed > budget.available: raise ValueError('Unearned updates')
    budget.completed = completed
    if not _same(state['budget'], dict(total=budget.total, completed=completed, receipts=budget._receipts)):
        raise ValueError('Update credit or receipt ledger changed')
    history = state['history']; canonical(history)  # Reject nonfinite JSON scalars.
    if len(history) != completed: raise ValueError('Missing update history')
    for total, steps in episode_boundaries:
        if steps != sum(_integer(r['audited_total']) <= total for r in history):
            raise ValueError('Episode update counter differs from published learning history')
    previous_total = 0
    for i, entry in enumerate(history, 1):
        total = _integer(entry['audited_total'])
        if (type(entry['critic_batches']) is not int or entry['critic_batches'] != i or
                total not in cumulative or total < previous_total or
                entry['credit_remaining'] != min(8250, max(total - 5000, 0) // 4) - i or
                entry['credit_remaining'] < 0 or entry['batch_rows'] != config['learning']['batch_size']):
            raise ValueError('Inconsistent update history')
        _integer(entry['active_rows'], 0, config['learning']['batch_size'])
        previous_total = total
    if sum(r['active_rows'] > 0 for r in history) != counts['actor']: raise ValueError('Actor count differs from active batches')
    updater = (ContactUpdater if contact else SACUpdater)(config)
    reference = updater._snapshot()
    if saved.keys() != reference.keys() or saved['policy'].keys() != reference['policy'].keys():
        raise ValueError('Missing policy or optimizer state')
    for key in reference['policy']: _tensor(saved['policy'][key], reference['policy'][key])
    _tensor(saved['alpha'], reference['alpha']); _tensor(saved['rng'], reference['rng'])
    # Validate the generator with a private object; no global RNG mutation.
    torch.Generator().set_state(saved['rng'])
    for key, optimizer in zip(('critic', 'actor', 'temperature'), updater._optimizers()):
        _optimizer(saved[key], optimizer, counts[key])
    updater._restore(deepcopy(saved)); updater._finite_state()
    from .admitted_collection import EngineeringSampler
    sampler = ContactSampler(config) if contact else EngineeringSampler(config)
    count = _integer(state['sampler']['count'])
    # Each initializer uses exactly two float64 uniform draws. Rejected duplicate
    # IDs can consume a draw without creating a new episode; preserve that stream.
    if contact:
        if count != len(attempts): raise ValueError('Contact sampler/attempt count mismatch')
        sampler.load_state(state['sampler'])
    else:
        sampler.rng.bit_generator.advance(2 * count)
        sampler.count = count
    if sampler.rng.bit_generator.state != state['sampler']['rng']: raise ValueError('Initializer RNG and count disagree')
    warmup, replay_rng = _rng(state['rng']['warmup']), _rng(state['rng']['replay'])
    return updater, replay, budget, sampler, warmup, replay_rng


def _flush_write(path, data):
    if isinstance(data, str): data = data.encode('utf-8')
    with path.open('xb') as f:
        f.write(data); f.flush(); os.fsync(f.fileno())


def save_checkpoint(chain, output):
    output = Path(output).resolve()
    if output.exists(): raise FileExistsError(output)
    state = capture(chain)
    validate_state(state, chain.admission)
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.with_name(output.name + '.pending-' + uuid.uuid4().hex)
    staging.mkdir()
    with (staging / 'state.pt').open('xb') as f:
        torch.save(state, f); f.flush(); os.fsync(f.fileno())
    manifest = dict(version='sac_checkpoint_manifest_v1', state_sha256=digest(staging / 'state.pt'))
    _flush_write(staging / 'manifest.json', canonical(manifest))
    chain.admission.verify()
    if output.exists(): raise FileExistsError(output)
    os.rename(staging, output)
    return digest(output / 'manifest.json')


def read_checkpoint(path, *, expected_digest, admission):
    path = Path(path).resolve()
    data = (path / 'manifest.json').read_bytes()
    if not expected_digest or hashlib.sha256(data).hexdigest() != expected_digest: raise ValueError('Checkpoint pin differs')
    manifest = json.loads(data)
    if manifest.get('version') != 'sac_checkpoint_manifest_v1': raise ValueError('Unknown checkpoint version')
    # Hash the very same bytes that are deserialized (avoid a second path read).
    import io
    payload = (path / 'state.pt').read_bytes()
    if hashlib.sha256(payload).hexdigest() != manifest['state_sha256']: raise ValueError('Checkpoint payload differs')
    state = torch.load(io.BytesIO(payload), map_location='cpu', weights_only=True)
    components = validate_state(state, admission)
    return state, components


def load_checkpoint(path, *, expected_digest, admission, output):
    output = Path(output).resolve()
    if output.exists(): raise FileExistsError(output)
    state, components = read_checkpoint(path, expected_digest=expected_digest, admission=admission)
    from .contact_execution import ContactAdmission, ContactCollection
    cls = ContactCollection if isinstance(admission, ContactAdmission) else SACCollection
    chain = cls(admission=admission, output=output)
    chain.updater, chain.replay, chain.budget, chain.sampler, chain.warmup.rng, chain.replay_rng = components
    chain.collector.updater, chain.collector.replay = chain.updater, chain.replay
    chain.collector.attempts = deepcopy(state['attempts'])
    chain.history = deepcopy(state['history'])
    # Carry durable receipts and all consumed IDs forward, including evicted episodes.
    for receipt in chain.collector.attempts:
        folder = output / receipt['episode_id']; folder.mkdir()
        _flush_write(folder / 'episode.json.gz', state['archives'][receipt['episode_id']])
        _flush_write(folder / 'status.json', canonical(receipt))
    admission.verify()
    return chain
