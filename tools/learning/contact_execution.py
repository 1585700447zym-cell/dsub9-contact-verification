"""Four-point chain: fresh sampling, fail closed, guard-clear publication only."""
from copy import deepcopy
import numpy as np
from .contact_contract import contact_config,validate_config,validate_case,ContactSampler,POINTS,guard_clear
from .contact_admission import ContactAdmission
from .admitted_collection import AdmittedCollector,_write_json,_write_archive
from .audited_replay import AuditedReplay
from .sac_collection import SACCollection,_LearningCollector,UpdateBudget,WarmupPolicy
from .sac_update import SACUpdater


class ContactUpdater(SACUpdater):
    config_validator=staticmethod(validate_config)


class ContactBudget(UpdateBudget):
    def __init__(self,config):
        validate_config(config); self.total=self.completed=0; self._receipts={}
    def record(self,receipt):
        if receipt.get('guard_clear') is not True: raise ValueError('Guard-clear receipt required')
        if receipt['episode_id'] not in self._receipts and self.total+receipt['committed']>=33000:
            raise ValueError('Whole-episode cycle bound exceeded')
        return super().record(receipt)


class ContactWarmup(WarmupPolicy):
    def __init__(self,config):
        validate_config(config)
        self.rng=np.random.Generator(np.random.PCG64(np.random.SeedSequence([config['sampling']['seed'],1])))


class ContactCollector(_LearningCollector):
    admission_type=ContactAdmission
    case_validator=staticmethod(validate_case)

    def _assert_frozen(self):
        if self.updater.counts!=self._start_counts or self.updater.fingerprints()!=self._start_fingerprints:
            raise RuntimeError('Learning state changed inside physical episode')

    def start(self,episode_id,*,case,seed):
        self._start_counts=deepcopy(self.updater.counts)
        self._start_fingerprints=self.updater.fingerprints()
        return super().start(episode_id,case=case,seed=seed)

    def collect(self,policy,steps,*,cut_at_end=False,deterministic=False):
        if cut_at_end: raise ValueError('Contact training requires whole episodes')
        self._assert_frozen()
        result=super().collect(policy,steps,deterministic=deterministic)
        self._assert_frozen()
        return result

    def _seal(self):
        # Hold references across finalize's destructive list clear; no second
        # finalize and no extra physical steps when interrupted during audit.
        self._seal_rows=list(self.buffer._pending or self.buffer.quarantined)
        facts=self.session.env.guard_facts
        from .episode_rules import rules_for
        if not rules_for(self.admission).guard_candidate(facts):
            self._fault_info=dict(self._fault_info or {},contact_publication_rejected=True)
        try: self._assert_frozen()
        except RuntimeError as exc: self._fault_info=dict(self._fault_info or {},policy_error=str(exc))
        try:
            result=super()._seal()
            self._seal_rows=[]
            return result
        except BaseException as exc:
            self.retain_failure(exc)
            raise

    def retain_failure(self,exc):
        self._blocked=True
        if not hasattr(self,'_folder') or getattr(self,'_failure_archived',None)==self._folder: return
        if self.session is None and self._pending is None: return
        if self._pending is not None:
            raw=deepcopy(self._pending)
        else:
            session=self.session; env=session.env
            buffer=getattr(self,'buffer',None)
            rows=getattr(self,'_seal_rows',None) or (buffer._pending or buffer.quarantined if buffer else [])
            raw=dict(episode_id=self._record['episode_id'],case=self._record['case'],seed=self._record['seed'],
                qualification_sha256=self.admission.expected_digest,transitions=deepcopy(rows),
                guard_facts=deepcopy(env.guard_facts),events=deepcopy(env.events),stop_samples=deepcopy(env.stop_samples),
                stop_time=session.stop_time,audit_end_time_s=float(env.data.time),
                final_session=dict(reason=session.reason,done=session.done),outcome=dict(valid_for_learning=False))
        raw.update(training_admitted=False,diagnostic_only=True,failure=repr(exc))
        raw['outcome']['valid_for_learning']=False
        _write_archive(self._folder/'failure_episode.json.gz',raw)
        self._failure_archived=self._folder

    def retry_publication(self):
        if self._pending is not None:
            clear=guard_clear(self._pending)
            total=getattr(self,'cycle_total',lambda:0)()
            if not 0 < len(self._pending['transitions']) <= 13000 or total+len(self._pending['transitions'])>=33000:
                clear=False
            if not clear: self._pending['outcome']['valid_for_learning']=False
            self._pending['guard_clear']=clear; self._record['guard_clear']=clear
            metadata=dict(optimizer_steps_start=self._start_counts['critic'],optimizer_steps=self.updater.counts['critic'],
                          policy_sha256=self._policy_sha,sampling_mode=self.sampling_mode)
            self._pending.update(metadata); self._record.update(metadata)
        return AdmittedCollector.retry_publication(self)


class ContactCollection(SACCollection):
    def __init__(self,*,admission,output):
        if not isinstance(admission,ContactAdmission): raise TypeError('Contact admission required')
        admission.verify(); self.admission=admission; self.config=admission.config
        self.updater=ContactUpdater(self.config); self.replay=AuditedReplay(capacity=100000)
        self.budget=ContactBudget(self.config); self.warmup=ContactWarmup(self.config)
        self.sampler=ContactSampler(self.config)
        self.replay_rng=np.random.Generator(np.random.PCG64(np.random.SeedSequence([self.config['sampling']['seed'],2])))
        self.collector=ContactCollector(admission=admission,replay=self.replay,output=output,updater=self.updater)
        self.collector.cycle_total=lambda:self.budget.total
        self.history=[]; self.failed=False

    def fail(self,exc):
        self.failed=True
        c=self.collector
        # Stop and retain an active physical attempt, including KeyboardInterrupt.
        if c.active:
            try: c._abort(exc)
            except BaseException: c._blocked=True
        try: c.retain_failure(exc)
        except BaseException as archive_exc:
            self.failure_archive_error=repr(archive_exc)
        c._blocked=True
        failure=dict(error=repr(exc),attempts=c.attempts,sampler_count=self.sampler.count,
                     updates=self.updater.counts,history=self.history,audited_total=self.budget.total)
        try: _write_json(c.output/'failure.json',failure)
        except OSError: pass  # Keep in-memory failure locked even when disk is unavailable.

    def start(self,episode_id,*,case=None):
        if (self.failed or self.collector.active or self.collector._blocked or self.budget.available or
            self.budget.total>=20000 or self.sampler.count>=6): raise RuntimeError('Contact start boundary/budget refused')
        if case is not None: raise ValueError('Training initialization must use the registered sampler')
        try:
            # Invalid IDs do not consume a draw; an attempted reset does.
            import re
            if not isinstance(episode_id,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',episode_id):
                raise ValueError('Invalid episode ID')
            if any(r['episode_id']==episode_id for r in self.collector.attempts): raise ValueError('Duplicate episode ID')
            super().start(episode_id)
        except BaseException as exc:
            self.fail(exc); raise

    def collect(self,steps,*,cut_at_end=False):
        if self.failed: raise RuntimeError('Contact chain failed')
        try: return super().collect(steps,cut_at_end=cut_at_end)
        except BaseException as exc:
            self.fail(exc); raise

    def update(self,max_batches):
        try: return super().update(max_batches)
        except BaseException as exc:
            self.fail(exc); raise

    def retry_publication(self):
        raise RuntimeError('Contact failures are retained; retry does not authorize continuation')
