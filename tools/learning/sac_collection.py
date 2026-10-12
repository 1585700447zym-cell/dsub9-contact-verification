"""Fresh collection to bounded SAC updates; no archive import or full trainer."""
from copy import deepcopy
import time

import numpy as np

from .admission import canonical, validate_config
from .admitted_collection import AdmittedCollector, EngineeringSampler
from .audited_replay import AuditedReplay
from .b2_sac_admission import SACAdmission, execution_contract
from .sac_update import SACUpdater


def qualified_update_limit(admission, record=None):
    record = admission.verify() if record is None else record
    if record.get('capability') == 'contact_four_point_execution':
        from .contact_execution import ContactAdmission, validate_config as contact_config_validator
        if not isinstance(admission, ContactAdmission): raise TypeError('Contact execution qualification required')
        contact_config_validator(admission.config)
        return admission.config['learning']['max_gradient_batches']
    if record.get('capability') == 'engineering_short_train':
        from .b2_training_admission import TrainingAdmission
        if (not isinstance(admission, TrainingAdmission) or record.get('runnable_trainer') is not True or
                any(record.get(k) is not True for k in ('collection_admitted', 'update_admitted', 'restore_admitted'))):
            raise ValueError('Explicit engineering training qualification required')
        validate_config(record['config'])
        return record['config']['learning']['max_gradient_batches']
    return execution_contract()['max_probe_updates']


class UpdateBudget:
    def __init__(self, config):
        validate_config(config)
        self.total = self.completed = 0
        self._receipts = {}

    @property
    def available(self): return min(8250, max(self.total - 5000, 0) // 4) - self.completed

    def record(self, receipt):
        if (not isinstance(receipt, dict) or not isinstance(receipt.get('episode_id'), str) or
                not receipt['episode_id'] or receipt.get('status') != 'published' or
                any(receipt.get(key) is not True for key in ('valid_for_learning', 'simulation_valid', 'physical_stopped')) or
                type(receipt.get('committed')) is not int or receipt['committed'] <= 0 or
                type(receipt.get('discarded')) is not int or receipt['discarded'] != 0):
            raise ValueError('Only a successful audited publication earns update credit')
        identity = receipt['episode_id']
        encoded = canonical(receipt)
        if identity in self._receipts:
            if self._receipts[identity] != encoded: raise ValueError('Publication receipt changed')
            return False
        self._receipts[identity] = encoded
        self.total += receipt['committed']
        return True

    def consume(self):
        if self.available <= 0: raise RuntimeError('No update credit')
        self.completed += 1


class WarmupPolicy:
    def __init__(self, config):
        validate_config(config)
        self.rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([config['sampling']['seed'], 1])))

    def predict(self, observation, deterministic=False):
        return self.rng.uniform(-1., 1., 4).astype(np.float32), None


class _LearningCollector(AdmittedCollector):
    def __init__(self, *, updater, **kwargs):
        self.updater = updater
        self.audit_archive_wall_s = 0.
        super().__init__(**kwargs)

    def _seal(self):
        start = time.perf_counter()
        try:
            return super()._seal()
        finally:
            self.audit_archive_wall_s += time.perf_counter() - start

    def start(self, episode_id, *, case, seed):
        self._start_count = self.updater.counts['critic']
        self._policy_sha = self.updater.fingerprints()['actor']
        super().start(episode_id, case=case, seed=seed)

    def retry_publication(self):
        if self._pending is not None:
            if self.updater.counts['critic'] != self._start_count:
                raise RuntimeError('Policy update occurred during unreviewed physical interaction')
            metadata = dict(optimizer_steps_start=self._start_count,
                optimizer_steps=self.updater.counts['critic'], policy_sha256=self._policy_sha,
                sampling_mode=self.sampling_mode)
            self._pending.update(metadata)
            self._record.update(metadata)
        return super().retry_publication()


class SACCollection:
    def __init__(self, *, admission, output):
        if not isinstance(admission, SACAdmission): raise TypeError('SAC update qualification required')
        admission.verify()
        self.admission = admission
        self.config = admission.config
        self.updater = SACUpdater(self.config)
        self.replay = AuditedReplay(capacity=self.config['learning']['replay_capacity'])
        self.budget = UpdateBudget(self.config)
        self.warmup = WarmupPolicy(self.config)
        self.sampler = EngineeringSampler(self.config)
        self.replay_rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([self.config['sampling']['seed'], 2])))
        self.collector = _LearningCollector(admission=admission, replay=self.replay, output=output, updater=self.updater)
        self.history = []
        self.failed = False

    def start(self, episode_id, *, case=None):
        if self.failed or self.updater.failed: raise RuntimeError('Learning chain failed')
        # Choose mode once per episode: unreviewed steps cannot end warmup.
        self.collector.sampling_mode = 'uniform_warmup' if self.budget.total < 5000 else 'sac_policy'
        selected = self.sampler.next_case() if case is None else case
        self.collector.start(episode_id, case=selected, seed=self.config['sampling']['seed'])

    def collect(self, steps, *, cut_at_end=False):
        policy = self.warmup if self.collector.sampling_mode == 'uniform_warmup' else self.updater
        result = self.collector.collect(policy, steps, cut_at_end=cut_at_end)
        if not self.collector.active: self.sync_publications()
        return result

    def sync_publications(self):
        for receipt in self.collector.attempts:
            if receipt['status'] == 'published': self.budget.record(receipt)
            elif receipt['status'] == 'rejected':
                self.failed = True
                raise RuntimeError('Rejected episode; inspect the retained attempt before continuing')

    def retry_publication(self):
        self.collector.retry_publication()
        self.sync_publications()

    def update(self, max_batches):
        if type(max_batches) is not int or max_batches <= 0: raise ValueError('Positive batch limit required')
        c = self.collector
        if (self.failed or self.updater.failed or c.active or c._blocked or
                c._pending is not None or c._status_pending):
            raise RuntimeError('Only an audited, published episode boundary permits updates')
        self.sync_publications()
        record = self.admission.verify()
        cap = qualified_update_limit(self.admission, record) - self.updater.counts['critic']
        count = min(max_batches, self.budget.available, cap)
        results = []
        for _ in range(count):
            rng = deepcopy(self.replay_rng.bit_generator.state)
            start = time.perf_counter()
            try:
                batch = self.replay.sample(self.config['learning']['batch_size'], rng=self.replay_rng)
                result = self.updater.update(batch)
            except Exception:
                self.replay_rng.bit_generator.state = rng
                self.failed = True
                raise
            self.budget.consume()
            result.update(wall_s=time.perf_counter() - start, audited_total=self.budget.total,
                credit_remaining=self.budget.available)
            self.history.append(result)
            results.append(result)
        self.admission.verify()
        return results
