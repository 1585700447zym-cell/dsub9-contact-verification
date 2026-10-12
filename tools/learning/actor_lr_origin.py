"""Pinned four-warmup origin and fixed draws; no execution admission or updates."""
from copy import deepcopy
import gzip
import hashlib
import io
import json
from pathlib import Path

import numpy as np
import torch
from .actor_lr_preparation import preparation_config, checkpoint_binding, PreparationUpdater, PARENT_CONFIG
from .admission import canonical
from .audited_replay import AuditedReplay
from .boundary_targets import BoundaryIndex
from .bounded_contact import SEED, BalancedSampler, EpisodeBudget
from .episode_rules import FORCE_ONLY
from .learning_rates import validate_optimizer_learning_rates
from .sac_checkpoint import _same, _replay_state


def read_pinned_state(path, manifest_pin):
    """Deserialize the same externally pinned bytes; does not admit execution."""
    path = Path(path)
    data = (path / 'manifest.json').read_bytes()
    if not manifest_pin or hashlib.sha256(data).hexdigest() != manifest_pin:
        raise ValueError('Checkpoint manifest pin differs')
    manifest = json.loads(data)
    payload = (path / 'state.pt').read_bytes()
    if (manifest.get('version') != 'bounded_checkpoint_manifest_v2' or
            hashlib.sha256(payload).hexdigest() != manifest.get('state_sha256')):
        raise ValueError('Checkpoint payload pin differs')
    return torch.load(io.BytesIO(payload), map_location='cpu', weights_only=True)


def _initial_stream(stream):
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence([SEED, stream])))


def _zero_updates(state):
    try:
        counts = state['updater']['counts']
        valid = (set(counts) == {'actor', 'critic', 'temperature', 'target'} and
            all(type(v) is int and v == 0 for v in counts.values()) and
            type(state['update_attempts']) is int and state['update_attempts'] == 0 and
            type(state['budget']['completed']) is int and state['budget']['completed'] == 0 and
            state['history'] == [] and
            all(state['updater'][role]['state'] == {} for role in ('actor', 'critic', 'temperature')))
    except (KeyError, TypeError):
        valid = False
    if not valid:
        raise ValueError('Exact zero-update origin with empty Adam state required')


def validate_warmup_metadata(raw, receipt, position, qualification_pin, policy_pin):
    if type(position) is not int or not 0 <= position < 4:
        raise ValueError('Four registered warmup episodes required')
    sampler = BalancedSampler()
    for _ in range(position+1):
        expected_case = sampler.next_case()
    expected = dict(episode_id=f'train_{position:02d}', case=expected_case, seed=SEED,
        qualification_sha256=qualification_pin, policy_sha256=policy_pin,
        sampling_mode='uniform_warmup', optimizer_steps=0, optimizer_steps_start=0)
    for key, value in expected.items():
        if not _same(raw.get(key), value) or not _same(receipt.get(key), value):
            raise ValueError('Warmup origin or receipt differs: ' + key)
    if not _same(raw['audit_end_time_s'], receipt['audit_end_time_s']):
        raise ValueError('Warmup receipt clock differs')
    size = len(raw['transitions'])
    if (receipt.get('status') != 'published' or not 0 < size <= 13000 or
            any(type(receipt.get(k)) is not int or receipt[k] != v for k,v in
                dict(steps=size, committed=size, discarded=0, evicted=0).items()) or
            not FORCE_ONLY.receipt_valid(receipt)):
        raise ValueError('Complete qualified warmup publication required')
    for key in ('simulation_valid', 'physical_stopped', 'valid_for_learning', 'task_outcome'):
        if not _same(receipt.get(key), raw['outcome'].get(key)):
            raise ValueError('Warmup raw outcome and receipt differ')
    if any(raw['outcome'].get(k) is not True for k in ('simulation_valid', 'physical_stopped', 'valid_for_learning')):
        raise ValueError('Warmup audit booleans required')


def verify_warmup_requests(requests, archived):
    try:
        observed = np.asarray(archived)
        valid = (isinstance(requests, np.ndarray) and requests.dtype == np.float32 and
            requests.ndim == 2 and requests.shape[1] == 4 and observed.shape == requests.shape and
            observed.dtype.kind in 'iuf' and np.isfinite(observed).all() and
            np.array_equal(requests.astype(np.float64), observed.astype(np.float64)))
    except (ValueError, TypeError, OverflowError):
        valid = False
    if not valid:
        raise ValueError('Warmup random requests differ from exact locked stream')


def rebuild_origin(initial, archive_pairs, qualification_pin):
    """Construct from audited archive bytes, never from a post-update checkpoint.

    The caller supplies externally pinned initial/receipt/archive bytes. This
    function re-audits their complete physics records without running physics.
    No binding, archived data, global RNG or initial checkpoint is modified.
    """
    _zero_updates(initial)
    if (initial.get('version') != 'force_only_checkpoint_v1' or
            initial['binding']['qualification_sha256'] != qualification_pin or
            not _same(initial['binding']['record']['config'], json.loads(PARENT_CONFIG.read_bytes())) or
            not _same(initial['replay'], dict(capacity=156000, size=0, seen=[], episodes=[])) or
            not _same(initial['budget'], dict(total=0, completed=0, receipts={})) or
            initial['sampler_count'] != 0 or initial['attempts'] != [] or initial['archives'] != {} or
            len(archive_pairs) != 4):
        raise ValueError('Pinned empty initial checkpoint and exactly four archives required')
    config = preparation_config('A')
    updater = PreparationUpdater(config)
    if not _same(initial['updater'], updater._snapshot()):
        raise ValueError('Initial weights, Adam, temperature or torch RNG differ from locked initialization')
    expected_rng = {key: _initial_stream(i).bit_generator.state for i,key in enumerate(('warmup','replay','boundary'),1)}
    if not _same(initial['rng'], expected_rng):
        raise ValueError('Initial independent RNG streams differ')
    replay, budget, index = AuditedReplay(capacity=156000), EpisodeBudget(rules=FORCE_ONLY), BoundaryIndex(rules=FORCE_ONLY)
    warmup = _initial_stream(1)
    archives, attempts = {}, []
    policy_pin = updater.fingerprints()['actor']
    for i, (receipt, compressed) in enumerate(archive_pairs):
        if not isinstance(compressed, bytes) or hashlib.sha256(compressed).hexdigest() != receipt.get('archive_sha256'):
            raise ValueError('Warmup archive digest differs')
        raw = json.loads(gzip.decompress(compressed))
        validate_warmup_metadata(raw, receipt, i, qualification_pin, policy_pin)
        FORCE_ONLY.classify(raw)
        result = replay.publish(raw['episode_id'], raw['transitions'], outcome=raw['outcome'], training_admitted=True)
        if any(not _same(receipt.get(k), v) for k,v in result.items()):
            raise ValueError('Warmup publication reconstruction differs')
        budget.record(deepcopy(receipt))
        index.add(raw)
        # A uniform action is drawn for every recorded control cycle, including
        # disabled phases. Check requests, not the permission-masked action.
        requests = warmup.uniform(-1., 1., (len(raw['transitions']), 4)).astype(np.float32)
        verify_warmup_requests(requests, [r['action_log']['raw_action'] for r in raw['transitions']])
        archives[raw['episode_id']] = compressed
        attempts.append(deepcopy(receipt))
    if len(replay) != 22766 or budget.available != 500 or budget.stop_reason:
        raise ValueError('Four-warmup origin credit or size differs')
    state = deepcopy(initial)
    state.update(version='actor_lr_origin_v1', replay=_replay_state(replay), archives=archives, attempts=attempts,
        budget=dict(total=budget.total, completed=0, receipts=budget._receipts), sampler_count=4,
        rng=dict(warmup=warmup.bit_generator.state, replay=expected_rng['replay'], boundary=expected_rng['boundary']))
    return state, index


def fork_origin(state, branch, source_manifest_pin):
    _zero_updates(state)
    if state.get('version') != 'actor_lr_origin_v1':
        raise ValueError('Registered reconstructed origin required')
    config = preparation_config(branch)
    result = deepcopy(state)
    validate_optimizer_learning_rates(result['updater'], preparation_config('A')['learning'])
    for group in result['updater']['actor']['param_groups']:
        group['lr'] = config['learning']['actor_learning_rate']
    result['comparison_binding'] = checkpoint_binding(config, source_manifest_pin)
    return result


def draw_plan(lengths, boundaries, streams, *, batches=500):
    if (type(batches) is not int or batches != 500 or len(lengths) != 4 or len(boundaries) != 4 or
            any(type(v) is not int or not 0 < v <= 13000 for v in lengths) or
            any(type(b) is not int or not 0 <= b < n for b,n in zip(boundaries, lengths))):
        raise ValueError('Registered four-warmup 500-batch plan required')
    rngs = {}
    for key in ('replay', 'boundary'):
        rngs[key] = _initial_stream(2 if key == 'replay' else 3)
        if streams.get(key) != rngs[key].bit_generator.state:
            raise ValueError('Zero-update draw stream required')
    ends = np.cumsum(lengths)
    starts = np.r_[0, ends[:-1]]
    result = []
    for i in range(500):
        uniform = rngs['replay'].integers(0, int(ends[-1]), size=256)
        selected = rngs['boundary'].integers(0, 4, size=16)
        owners = np.searchsorted(ends, uniform, side='right')
        base = [[f'train_{int(o):02d}', int(v-starts[o])] for o,v in zip(owners, uniform)]
        critic = base[:240]+[[f'train_{int(j):02d}', boundaries[int(j)]] for j in selected]
        result.append(dict(batch=i+1, actor_flat_indices=uniform.tolist(), boundary_episode_indices=selected.tolist(), critic_indices=critic))
    return dict(version='actor_lr_fixed_draw_plan_v1', batches=result, initial_rng=deepcopy(streams),
        final_rng={key:value.bit_generator.state for key,value in rngs.items()})
