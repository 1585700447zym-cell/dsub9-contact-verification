"""Matched new-data SAC branches and complete, versioned checkpoint recovery.

No physical or learning work occurs at import. Source archives are always
requalified under this stage's permission rules; old replay is never imported.
"""
from copy import deepcopy
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import uuid

import numpy as np
import torch
import paired_contract as C
from stage_rules import StageRules
from tools.learning.audited_replay import AuditedReplay
from tools.learning.boundary_targets import BoundaryIndex
from tools.learning.sac_update import SACUpdater
from tools.learning.sac_checkpoint import _same, _tensor, _optimizer, _replay_state, _flush_write

CHECKPOINT_VERSION = 'stage_permission_learning_checkpoint_v1'
MANIFEST_VERSION = 'stage_permission_checkpoint_manifest_v1'
DATASET_VERSION = 'stage_permission_dataset_v1'
CASE_NAMES = ('x_pos_100', 'x_neg_100', 'y_pos_100', 'y_neg_100')
CAPACITY = 8 * 13000


def _arm(arm):
    if arm not in ('F', 'S'):
        raise ValueError('Registered F/S permission mode required')
    return arm


def _identity(row):
    source = row.get('identity', row)
    return {key: source[key] for key in ('id', 'stage', 'arm', 'case_index', 'case')}


def _archive_path(relative):
    path = (C.ROOT / relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(C.ROOT.resolve()):
        raise ValueError('Stage archive must be inside the bound workspace')
    return path


def _source(raw, arm, role, index, batches, binding_pin):
    """Identity and admission checks independent of the physical rules audit."""
    _arm(arm)
    identity = raw.get('current_identity', {})
    expected_id = f'{role}_{arm}_{CASE_NAMES[index]}'
    if (role not in ('warmup', 'online') or raw.get('episode_id') != expected_id or
            identity.get('id') != expected_id or identity.get('stage') != role or
            identity.get('arm') != arm or identity.get('case_index') != index or
            C.canonical(identity.get('case')) != C.canonical(raw.get('case')) or
            raw.get('case', {}).get('name') != CASE_NAMES[index] or
            raw.get('seed') != C.scope()['seed'] or raw.get('stage_mode') != arm or
            raw.get('qualification_sha256') != C.source_binding(arm, role, binding_pin) or
            raw.get('training_admitted') is not True or raw.get('fault') is not None or
            any(type(raw.get(key)) is not int or raw[key] != batches
                for key in ('optimizer_steps_start', 'optimizer_steps')) or
            any(raw.get('outcome', {}).get(key) is not True
                for key in ('simulation_valid', 'physical_stopped', 'valid_for_learning'))):
        raise ValueError('New matched arm/archive/admission/update identity required')
    facts = raw.get('guard_facts', {})
    if any(facts.get(key) != [] for key in ('contact_reasons', 'motion_reasons', 'invalid_reasons')):
        raise ValueError('Guarded archive cannot earn further learning credit')
    return StageRules(arm).classify(raw)


def verify_dataset_bytes(manifest, data, manifest_pin):
    if (type(data) is not bytes or hashlib.sha256(data).hexdigest() != manifest_pin or
            C.canonical(json.loads(data)) != C.canonical(manifest)):
        raise ValueError('Exact persisted dataset bytes/qualification changed')


def _dataset_identity(manifest, arm, ledger, manifest_pin):
    if (manifest.get('version') != DATASET_VERSION or manifest.get('arm') != arm or
            manifest.get('binding_sha256') != ledger.state['binding_sha256'] or
            manifest.get('authorization_sha256') != ledger.state['authorization_sha256'] or
            manifest.get('permission_version') != StageRules(arm).version or
            C.canonical(manifest.get('config')) != C.canonical(C.config(arm)) or
            len(manifest.get('references', [])) != 4):
        raise ValueError('Current complete branch dataset binding required')
    registered = ledger.state['datasets'].get(arm, {})
    if (registered.get('manifest_sha256') != manifest_pin or
            registered.get('ids') != [ref['id'] for ref in manifest['references']]):
        raise ValueError('Dataset differs from durable qualification')


def qualify_dataset(arm, ledger, output):
    """Qualify exactly this run's four new, unguarded warmup archives."""
    _arm(arm)
    ledger.healthy()
    if arm in ledger.state['datasets']:
        raise ValueError('Dataset already qualified; no duplicate credit')
    rows = ledger.rows('warmup', arm)
    if len(rows) != 4 or sorted(_identity(row)['case_index'] for row in rows) != list(range(4)):
        raise ValueError('Four unique matched warmup directions required')
    rows = sorted(rows, key=lambda row: _identity(row)['case_index'])
    refs, receipts = [], []
    for index, row in enumerate(rows):
        identity = _identity(row)
        if (identity['stage'] != 'warmup' or identity['arm'] != arm or row.get('completed') is not True or
                row.get('guard_hit') is not False or row.get('simulation_valid') is not True or
                row.get('physical_stopped') is not True):
            raise ValueError('Complete successful audit, not task success, is required')
        path = _archive_path(row['archive_path'])
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != row['archive_sha256']:
            raise ValueError('Warmup archive bytes changed')
        raw = json.loads(gzip.decompress(data))
        stamp = _source(raw, arm, 'warmup', index, 0, ledger.state['binding_sha256'])
        if C.canonical(_identity(raw['current_identity'])) != C.canonical(identity):
            raise ValueError('Ledger and raw warmup identities differ')
        AuditedReplay(capacity=13000)._prepare(raw['transitions'])
        refs.append(dict(id=identity['id'], path=row['archive_path'], sha256=row['archive_sha256'], role='warmup'))
        receipts.append(dict(episode_id=identity['id'], stage_mode=arm, training_admitted=True,
                             archive_sha256=row['archive_sha256'], learning_eligibility=stamp,
                             committed=len(raw['transitions']), discarded=0))
    manifest = dict(version=DATASET_VERSION, arm=arm, config=C.config(arm),
                    permission_version=StageRules(arm).version, binding_sha256=ledger.state['binding_sha256'],
                    authorization_sha256=ledger.state['authorization_sha256'], references=refs,
                    current_receipts=receipts, historical_replay_imported=False)
    path = Path(output) / f'dataset_{arm}.json'
    if path.exists():
        raise FileExistsError('Dataset publication already exists')
    C.write(path, manifest)
    manifest_pin = C.digest(path)
    ledger.register_dataset(arm, manifest_pin, [ref['id'] for ref in refs])
    return manifest, manifest_pin


class Updater(SACUpdater):
    @staticmethod
    def config_validator(config):
        if not any(C.canonical(config) == C.canonical(C.config(arm)) for arm in ('F', 'S')):
            raise ValueError('Exact current permission-specific SAC configuration required')


def zero_updater(arm):
    """Reuse only the sealed zero updater, never its replay or draw plan."""
    from tools.learning.actor_lr_engine import read_origin
    state, _ = read_origin()
    saved = state['updater']
    if any(saved['counts'].values()) or any(saved[key]['state'] for key in ('actor', 'critic', 'temperature')):
        raise ValueError('Zero update/empty Adam origin required')
    updater = Updater(C.config(_arm(arm)))
    updater._restore(deepcopy(saved))
    updater._finite_state()
    return updater


def rng(stream):
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence([C.scope()['seed'], stream])))


def index_state(index):
    return {key: dict(targets=torch.tensor(value[0].copy()), mask=torch.tensor(value[1].copy()), boundary=value[2])
            for key, value in index.entries.items()}


def sample_signature(indices):
    return hashlib.sha256(C.canonical([list(item) for item in indices]).encode()).hexdigest()


def validate_counts(counts, history, completed):
    if (type(completed) is not int or not 0 <= completed <= 2500 or
            set(counts) != {'critic', 'target', 'actor', 'temperature'} or
            any(type(value) is not int or not 0 <= value <= 2500 for value in counts.values()) or
            counts['critic'] != completed or counts['target'] != completed or len(history) != completed or
            any(type(row.get('active_rows')) is not int or not 0 <= row['active_rows'] <= 256 or
                row.get('critic_batches') != i or row.get('batch_rows') != 256
                for i, row in enumerate(history, 1)) or
            counts['actor'] != counts['temperature'] or
            counts['actor'] != sum(row['active_rows'] > 0 for row in history)):
        raise ValueError('Optimizer, update history and permission counts disagree')
    C.canonical(history)


class Branch:
    def __init__(self, arm, ledger, manifest, manifest_pin, updater=None, dataset_bytes=None):
        self.arm = _arm(arm)
        self.ledger = ledger
        self.manifest, self.manifest_pin = deepcopy(manifest), manifest_pin
        self.dataset_bytes = ((C.HERE/'run'/f'dataset_{arm}.json').read_bytes()
                              if dataset_bytes is None else dataset_bytes)
        verify_dataset_bytes(self.manifest, self.dataset_bytes, manifest_pin)
        _dataset_identity(self.manifest, arm, ledger, manifest_pin)
        self.updater = zero_updater(arm) if updater is None else updater
        if C.canonical(self.updater.config) != C.canonical(C.config(arm)) or self.updater.failed:
            raise ValueError('Healthy updater must use this exact branch configuration')
        self.replay = AuditedReplay(capacity=CAPACITY)
        self.index = BoundaryIndex(rules=StageRules(arm))
        self.replay_rng, self.boundary_rng = rng(2), rng(3)
        self.history, self.refs, self.archives = [], [], {}
        self.failed = False
        for ref in manifest['references']:
            self._append_audited(ref, _archive_path(ref['path']).read_bytes(), 0)

    def _append_audited(self, ref, data, expected_batches):
        """Private rebuild primitive; public append additionally checks live credit."""
        if (type(data) is not bytes or ref['id'] in self.archives or
                hashlib.sha256(data).hexdigest() != ref['sha256']):
            raise ValueError('Repeated or changed learning archive')
        role = ref.get('role')
        index = len(self.refs) if role == 'warmup' else len(self.refs)-4
        if (role not in ('warmup', 'online') or not 0 <= index < 4 or
                expected_batches != (0 if role == 'warmup' else 500*(index+1))):
            raise ValueError('Archive role/order/update boundary differs')
        if role == 'warmup' and ref != self.manifest['references'][index]:
            raise ValueError('Warmup differs from current dataset qualification')
        raw = json.loads(gzip.decompress(data))
        _source(raw, self.arm, role, index, expected_batches, self.ledger.state['binding_sha256'])
        if ref['id'] != raw['episode_id']:
            raise ValueError('Reference and archive identity differ')
        _archive_path(ref['path'])
        # Validate both builders before mutating either replay or index.
        self.replay._prepare(raw['transitions'])
        from tools.learning.boundary_targets import exact_tail
        exact_tail(raw, rules=StageRules(self.arm))
        result = self.replay.publish(ref['id'], raw['transitions'], outcome=raw['outcome'], training_admitted=True)
        if result['committed'] != len(raw['transitions']) or result['evicted']:
            raise ValueError('Whole current-stage replay publication required')
        self.index.add(raw)
        self.refs.append(deepcopy(ref))
        self.archives[ref['id']] = data

    def append_archive(self, ref, data, expected_batches):
        self.ledger.healthy()
        if (self.failed or self.updater.failed or ref.get('role') != 'online' or
                expected_batches != len(self.history) or self.updater.counts['critic'] != expected_batches or
                self.ledger.state['updates'][self.arm]['completed'] != expected_batches):
            raise ValueError('Online archive needs exact earned live update boundary')
        self._append_audited(ref, data, expected_batches)

    def update_one(self, meter):
        n = len(self.history)
        if (self.failed or self.updater.failed or self.updater.counts['critic'] != n or
                self.ledger.state['updates'][self.arm]['completed'] != n or
                len(self.refs) != 4+n//500 or n >= 2500):
            raise RuntimeError('Healthy synchronized replay/update boundary required')
        token = self.ledger.reserve_update(self.arm)
        try:
            meter.begin_update(token)
            batch = self.index.sample(self.replay, rng=self.replay_rng, boundary_rng=self.boundary_rng)
            row = self.updater.update(batch.actor, critic_batch=batch.critic, exact_targets=(batch.targets, batch.mask))
            row.update(episode_count=len(self.refs), replay_size=len(self.replay),
                       critic_sample_sha256=sample_signature(batch.indices))
            self.history.append(row)
            self.ledger.finish_update(token)
            return row
        except BaseException:
            self.failed = True
            raise
        finally:
            meter.end_context()

    def capture(self):
        self.ledger.healthy()
        n = len(self.history)
        if (self.failed or self.updater.failed or
                self.ledger.state['updates'][self.arm] != dict(attempted=n, completed=n)):
            raise RuntimeError('Healthy complete durable update boundary required')
        validate_counts(self.updater.counts, self.history, n)
        _dataset_identity(self.manifest, self.arm, self.ledger, self.manifest_pin)
        return deepcopy(dict(version=CHECKPOINT_VERSION, arm=self.arm, config=C.config(self.arm),
            permission_version=StageRules(self.arm).version, binding_sha256=self.ledger.state['binding_sha256'],
            authorization_sha256=self.ledger.state['authorization_sha256'], dataset=self.manifest,
            dataset_bytes=self.dataset_bytes, dataset_sha256=self.manifest_pin, updater=self.updater._snapshot(),
            replay=_replay_state(self.replay), boundary_index=index_state(self.index), references=self.refs,
            archives=self.archives, history=self.history,
            rng=dict(replay=self.replay_rng.bit_generator.state, boundary=self.boundary_rng.bit_generator.state)))

    def save(self, path):
        path = Path(path)
        if path.exists():
            raise FileExistsError('Checkpoint already exists')
        state = self.capture()
        n = len(self.history)
        if n % 500:
            raise ValueError('Only registered 500-batch boundaries may be saved')
        path.parent.mkdir(parents=True, exist_ok=True)
        staging = path.with_name(path.name+'.staging-'+uuid.uuid4().hex)
        staging.mkdir()
        with (staging/'state.pt').open('xb') as stream:
            torch.save(state, stream)
            stream.flush()
            os.fsync(stream.fileno())
        manifest = dict(version=MANIFEST_VERSION, arm=self.arm, permission_version=StageRules(self.arm).version,
                        binding_sha256=state['binding_sha256'], authorization_sha256=state['authorization_sha256'],
                        state_sha256=C.digest(staging/'state.pt'), batches=n, dataset_sha256=self.manifest_pin)
        _flush_write(staging/'manifest.json', json.dumps(manifest, sort_keys=True, allow_nan=False, indent=2).encode('utf-8'))
        if path.exists():
            raise FileExistsError('Checkpoint already exists')
        os.rename(staging, path)
        return C.digest(path/'manifest.json')


def check_snapshot_identity(saved, arm, binding_pin, auth_pin):
    if (saved.get('version') != CHECKPOINT_VERSION or saved.get('arm') != arm or
            saved.get('permission_version') != StageRules(arm).version or
            saved.get('binding_sha256') != binding_pin or saved.get('authorization_sha256') != auth_pin or
            C.canonical(saved.get('config')) != C.canonical(C.config(arm))):
        raise ValueError('Checkpoint permission/configuration/authority changed')


def restore(path, manifest_pin, arm, ledger):
    """Rebuild every data/state component at 0/500/.../2500; zero model calls."""
    _arm(arm)
    ledger.healthy()
    path = Path(path)
    if C.digest(path/'manifest.json') != manifest_pin:
        raise ValueError('Checkpoint manifest changed')
    manifest = C.read(path/'manifest.json')
    n = manifest.get('batches')
    if (manifest.get('version') != MANIFEST_VERSION or manifest.get('arm') != arm or
            manifest.get('permission_version') != StageRules(arm).version or
            manifest.get('binding_sha256') != ledger.state['binding_sha256'] or
            manifest.get('authorization_sha256') != ledger.state['authorization_sha256'] or
            type(n) is not int or not 0 <= n <= 2500 or n % 500 or
            ledger.state['updates'][arm] != dict(attempted=n, completed=n)):
        raise ValueError('Registered complete checkpoint boundary required')
    data = (path/'state.pt').read_bytes()
    if hashlib.sha256(data).hexdigest() != manifest['state_sha256']:
        raise ValueError('Checkpoint payload changed')
    saved = torch.load(io.BytesIO(data), map_location='cpu', weights_only=True)
    check_snapshot_identity(saved, arm, ledger.state['binding_sha256'], ledger.state['authorization_sha256'])
    verify_dataset_bytes(saved['dataset'], saved['dataset_bytes'], saved['dataset_sha256'])
    _dataset_identity(saved['dataset'], arm, ledger, saved['dataset_sha256'])
    if saved['dataset_sha256'] != manifest['dataset_sha256']:
        raise ValueError('Checkpoint dataset pin differs')
    refs, archives = saved['references'], saved['archives']
    minimum = 4+min(4, max(0, (n-1)//500))
    maximum = 4+min(4, n//500)
    if (not minimum <= len(refs) <= maximum or len(archives) != len(refs) or
            set(archives) != {ref['id'] for ref in refs}):
        raise ValueError('Checkpoint lacks exact eligible episode prefix')
    updater = Updater(C.config(arm))
    branch = Branch.__new__(Branch)
    branch.arm, branch.ledger = arm, ledger
    branch.manifest, branch.manifest_pin = saved['dataset'], saved['dataset_sha256']
    branch.dataset_bytes, branch.updater = saved['dataset_bytes'], updater
    branch.replay, branch.index = AuditedReplay(capacity=CAPACITY), BoundaryIndex(rules=StageRules(arm))
    branch.refs, branch.archives, branch.history = [], {}, saved['history']
    branch.failed = False
    for i, ref in enumerate(refs):
        branch._append_audited(ref, archives[ref['id']], 0 if i < 4 else (i-3)*500)
    if not _same(_replay_state(branch.replay), saved['replay']) or not _same(index_state(branch.index), saved['boundary_index']):
        raise ValueError('Replay or boundary targets differ from complete raw archives')
    validate_counts(saved['updater']['counts'], branch.history, n)
    rr, br = rng(2), rng(3)
    episodes = branch.replay._state.episodes
    for i, row in enumerate(branch.history):
        count = 4+i//500
        prefix = episodes[:count]
        keys = [key for key, _ in prefix]
        ends = np.cumsum([len(array['rewards']) for _, array in prefix])
        starts = np.r_[0, ends[:-1]]
        draws = rr.integers(0, int(ends[-1]), size=256)
        owners = np.searchsorted(ends, draws, side='right')
        base = tuple((keys[owner], int(draw-starts[owner])) for owner, draw in zip(owners, draws))
        candidates = [(key, branch.index.entries[key][2]) for key in keys if branch.index.entries[key][2] is not None]
        if not candidates:
            raise ValueError('Historical update has no legal decision boundary')
        boundary = tuple(candidates[int(j)] for j in br.integers(0, len(candidates), size=16))
        arrays = dict(prefix)
        active = sum(bool(arrays[key]['action_active'][j, 0]) for key, j in base)
        if (row.get('episode_count') != count or row.get('replay_size') != int(ends[-1]) or
                row['active_rows'] != active or row.get('critic_sample_sha256') != sample_signature(base[:240]+boundary)):
            raise ValueError('Training draw, episode prefix or permission history differs')
    if rr.bit_generator.state != saved['rng']['replay'] or br.bit_generator.state != saved['rng']['boundary']:
        raise ValueError('Sampling RNG endpoint differs')
    reference, learned = updater._snapshot(), saved['updater']
    if learned.keys() != reference.keys() or learned['policy'].keys() != reference['policy'].keys():
        raise ValueError('Missing complete updater state')
    for key in reference['policy']:
        _tensor(learned['policy'][key], reference['policy'][key])
    _tensor(learned['alpha'], reference['alpha'])
    _tensor(learned['rng'], reference['rng'])
    torch.Generator().set_state(learned['rng'])
    for key, optimizer in zip(('critic', 'actor', 'temperature'), updater._optimizers()):
        _optimizer(learned[key], optimizer, learned['counts'][key])
    if n == 0 and not _same(learned, zero_updater(arm)._snapshot()):
        raise ValueError('Zero checkpoint weights or random stream differ from sealed common origin')
    updater._restore(deepcopy(learned))
    updater._finite_state()
    branch.replay_rng, branch.boundary_rng = rr, br
    if not _same(branch.capture(), saved):
        raise ValueError('Complete restored learning state differs')
    return branch
