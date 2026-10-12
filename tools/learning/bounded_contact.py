"""The approved single-seed, twelve-episode experiment; no implicit launch."""
from copy import deepcopy
import gzip
import json
import math
from pathlib import Path
import time
import numpy as np
from .runtime import ROOT
from .admission import canonical, digest, verify_files
from .contact_contract import contact_config, guard_clear
from .contact_execution import ContactCollector, ContactCollection
from .admitted_collection import AdmittedCollector, _write_json
from .audited_replay import AuditedReplay
from .sac_collection import UpdateBudget, WarmupPolicy, SACCollection
from .sac_update import SACUpdater
from .boundary_targets import BoundaryIndex
from .episode_rules import STRICT, rules_for, stamp_pending

DELIVERY=ROOT/'deliverables/learning_chain/b2_bounded_cycle_20260927'
CONFIG=ROOT/'docs/stage_b/四点接触有限训练配置_v2.json'
POINTS=((.0001,0.),(-.0001,0.),(0.,.0001),(0.,-.0001))
HOLDOUT=((.000095,0.),(-.000095,0.),(0.,.000095),(0.,-.000095))
SEED=2026092716


def bounded_config():
    c=contact_config(); c['version']='bounded_contact_cycle_v2'
    c['domain'].update(distribution='balanced_three_rounds',points_xy_m=[list(p) for p in POINTS])
    for k in ('target_cycles',): c['sampling'].pop(k,None)
    c['sampling'].update(seed=SEED,max_attempts=12,total_audited_cycles_upper_bound=156000,
        rng_streams=dict(warmup=1,replay=2,boundary=3),stop_at='twelve_complete_audited_episodes')
    for k in ('warmup_audited_transitions','gradient_batches_per_audited_transition'): c['learning'].pop(k,None)
    c['learning'].update(seed=SEED,replay_capacity=156000,max_gradient_batches=4500,
        warmup_episodes=4,batches_per_boundary=500,critic_boundary_rows=16,exact_terminal_tail=True)
    c['execution'].update(evaluate='initial_final_restored_and_frozen_four_holdout',independent_test_used=False)
    return c


def validate_config(config):
    if canonical(config)!=canonical(bounded_config()): raise ValueError('Unregistered bounded configuration')


def case_at(name,x,y):
    return dict(name=name,x_offset_m=x,y_offset_m=y,roll_rad=0.,pitch_rad=0.,start_origin_z_m=-.004,target_depth_m=.004)


def validate_case(case,*,training=False):
    fields=('x_offset_m','y_offset_m','roll_rad','pitch_rad','start_origin_z_m','target_depth_m')
    if (not isinstance(case,dict) or any(type(case.get(k)) not in (float,int) or not math.isfinite(case[k]) for k in fields)
        or (case['x_offset_m'],case['y_offset_m']) not in (POINTS if training else POINTS+HOLDOUT)
        or case['roll_rad']!=0 or case['pitch_rad']!=0 or case['start_origin_z_m']!=-.004 or case['target_depth_m']!=.004):
        raise ValueError('Case outside registered finite scope')


def current_sources():
    from tools.validation.verify_residual_interface import all_sources
    result=all_sources(); result[CONFIG.relative_to(ROOT).as_posix()]=digest(CONFIG)
    return result


class BoundedAdmission:
    def __init__(self,path,*,expected_digest):
        self.path=Path(path); self.expected_digest=expected_digest; self.verify()
    @property
    def config(self): return deepcopy(self._record['config'])
    def verify(self,case=None):
        from tools.validation.verify_residual_interface import qualified_runtime
        if not self.expected_digest or digest(self.path)!=self.expected_digest: raise ValueError('Admission pin changed')
        r=json.loads(self.path.read_text(encoding='utf-8'))
        if (r.get('capability')!='bounded_contact_cycle_v2' or r.get('synthetic_only') is not False or
                any(r.get(k) is not True for k in ('collection_admitted','update_admitted','restore_admitted'))):
            raise ValueError('Bounded execution admission required')
        validate_config(r['config'])
        if r['source_sha256']!=current_sources(): raise ValueError('Execution source changed')
        verify_files(ROOT,r['evidence_sha256'])
        if canonical(r['runtime'])!=canonical(qualified_runtime(ROOT/'tmp/mujoco_3_13_probe')):
            raise ValueError('Qualified runtime changed')
        if case is not None: validate_case(case)
        self._record=r; return deepcopy(r)


class BalancedSampler:
    def __init__(self): self.count=0
    def next_case(self):
        if self.count>=12: raise RuntimeError('Twelve-attempt budget exhausted')
        c=case_at(f'train_{self.count:02d}',*POINTS[self.count%4]); self.count+=1; return c


class EpisodeBudget(UpdateBudget):
    def __init__(self, *, rules=STRICT):
        self.total=self.completed=0; self._receipts={}; self.rules=rules
    @property
    def stop_reason(self):
        return self.rules.stop_reason([json.loads(r) for r in self._receipts.values()])
    @property
    def available(self): return 0 if self.stop_reason else max(0,len(self._receipts)-3)*500-self.completed
    def record(self,receipt):
        key=receipt.get('episode_id')
        if self.stop_reason: raise RuntimeError('Force failure frequency stop')
        if key not in self._receipts and (len(self._receipts)>=12 or self.available or
                type(receipt.get('committed')) is not int or not 0<receipt['committed']<=13000):
            raise ValueError('Invalid episode boundary or unspent credit')
        if not self.rules.receipt_valid(receipt): raise ValueError('Eligible audited receipt required')
        return super().record(receipt)


class ForceFailureStop(RuntimeError):
    """A published task failure reached the registered administrative limit."""
    def __init__(self,reason,episode_id):
        super().__init__(reason)
        self.reason=reason; self.episode_id=episode_id
    def record(self):
        return dict(kind='force_failure_frequency',reason=self.reason,episode_id=self.episode_id)


class RunLedger:
    CAPS=dict(initial=4,training=12,final=4,restored=4,holdout_b2=4,holdout_sac=4)
    def __init__(self,path):
        self.path=Path(path)
        self.state=json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else dict(
            dynamic_starts=0,attempts=[],status='healthy',active=None)
    def start(self,stage,identity):
        s=self.state
        if (s['status']!='healthy' or s['active'] is not None or stage not in self.CAPS or
            s['dynamic_starts']>=32 or sum(r['stage']==stage for r in s['attempts'])>=self.CAPS[stage] or
            any(r['stage']==stage and r['id']==identity for r in s['attempts'])):
            raise RuntimeError('Persistent start budget or unhealthy boundary refused')
        entry=dict(stage=stage,id=identity,status='started'); s['attempts'].append(entry)
        s.update(dynamic_starts=s['dynamic_starts']+1,active=len(s['attempts'])-1)
        _write_json(self.path,s)
    def finish(self,result):
        if self.state['active'] is None: raise RuntimeError('No active start')
        self.state['attempts'][self.state['active']].update(status='finished',result=result)
        self.state['active']=None; _write_json(self.path,self.state)
    def fail(self,error):
        self.state.update(status='failed',error=str(error)); _write_json(self.path,self.state)
    def stop(self,exc):
        if (not isinstance(exc,ForceFailureStop) or self.state['active'] is not None
                or not self.state['attempts'] or self.state['attempts'][-1]['id']!=exc.episode_id
                or self.state['attempts'][-1]['status']!='finished'):
            raise RuntimeError('Controlled stop requires the completed threshold episode')
        self.state.update(status='stopped',stop_kind='force_failure_frequency',stop_reason=exc.reason)
        _write_json(self.path,self.state)


class BoundedUpdater(SACUpdater):
    config_validator=staticmethod(validate_config)


class BoundedCollector(ContactCollector):
    admission_type=BoundedAdmission
    case_validator=staticmethod(validate_case)
    def retain_failure(self,exc):
        if self.session is None and self._pending is None and hasattr(self,'_folder'):
            self._blocked=True
            _write_json(self._folder/'failure_before_session.json',dict(error=repr(exc),attempt=self._record))
            return
        return super().retain_failure(exc)
    def retry_publication(self):
        if self._pending is not None:
            raw=self._pending
            metadata=dict(optimizer_steps_start=self._start_counts['critic'],optimizer_steps=self.updater.counts['critic'],
                          policy_sha256=self._policy_sha,sampling_mode=self.sampling_mode)
            raw.update(metadata); self._record.update(metadata)
            stamp_pending(raw,self._record,rules_for(self.admission))
        return AdmittedCollector.retry_publication(self)


class BoundedCollection:
    def __init__(self,*,admission,output):
        if not isinstance(admission,BoundedAdmission): raise TypeError('Bounded admission required')
        admission.verify(); self.admission=admission; self.config=admission.config
        self.updater=getattr(admission,'updater_type',BoundedUpdater)(self.config); self.replay=AuditedReplay(capacity=156000)
        self.budget=EpisodeBudget(rules=rules_for(admission)); self.sampler=BalancedSampler()
        self.index=BoundaryIndex(rules=rules_for(admission))
        self.warmup=object.__new__(WarmupPolicy)
        self.warmup.rng=np.random.Generator(np.random.PCG64(np.random.SeedSequence([SEED,1])))
        self.replay_rng=np.random.Generator(np.random.PCG64(np.random.SeedSequence([SEED,2])))
        self.boundary_rng=np.random.Generator(np.random.PCG64(np.random.SeedSequence([SEED,3])))
        self.collector=BoundedCollector(admission=admission,replay=self.replay,output=output,updater=self.updater)
        self.history=[]; self.failed=False; self.update_attempts=0
    def fail(self,exc):
        if not isinstance(exc,ForceFailureStop):
            return ContactCollection.fail(self,exc)
        # Lock the chain without relabelling a fully audited, published task as
        # a runtime fault, or modifying its archive/receipt after publication.
        self.failed=True; self.collector._blocked=True
        _write_json(self.collector.output/'controlled_stop.json',dict(**exc.record(),
            attempts=self.collector.attempts,updates=self.updater.counts,audited_total=self.budget.total))
    def record_update_budget(self):
        _write_json(self.collector.output/'update_budget.json',dict(attempted=self.update_attempts,
            completed=self.budget.completed,failed_or_invalidated=self.update_attempts-self.budget.completed,
            remaining=4500-self.update_attempts))
    def start(self,episode_id):
        c=self.collector
        if self.failed or c.active or c._blocked or self.budget.available or self.budget.stop_reason: raise RuntimeError('Unhealthy start boundary')
        expected=f'train_{self.sampler.count:02d}'
        if episode_id!=expected: raise ValueError('Registered episode order required')
        case=self.sampler.next_case(); validate_case(case,training=True)
        c.sampling_mode='uniform_warmup' if self.sampler.count<=4 else 'sac_policy'
        try: c.start(episode_id,case=case,seed=SEED)
        except BaseException as exc: self.fail(exc); raise
    def collect(self,steps):
        c=self.collector
        if self.failed: raise RuntimeError('Failed chain')
        try:
            policy=self.warmup if c.sampling_mode=='uniform_warmup' else self.updater
            result=c.collect(policy,steps)
            if not c.active:
                receipt=c.attempts[-1]
                if receipt['status']!='published' or c._blocked: raise RuntimeError('Physical audit failed')
                self.budget.record(receipt)
                raw=json.loads(gzip.decompress((c.output/receipt['episode_id']/'episode.json.gz').read_bytes()))
                self.index.add(raw)
                if self.budget.stop_reason: raise ForceFailureStop(self.budget.stop_reason,receipt['episode_id'])
            return result
        except BaseException as exc: self.fail(exc); raise
    def update(self,max_batches):
        c=self.collector
        if (type(max_batches) is not int or max_batches<=0 or self.failed or self.budget.stop_reason or c.active or c._blocked or
            c._pending is not None or c._status_pending): raise RuntimeError('Healthy audited update boundary required')
        self.admission.verify(); results=[]
        for _ in range(min(max_batches,self.budget.available,4500-self.update_attempts)):
            start=time.perf_counter()
            try:
                b=self.index.sample(self.replay,rng=self.replay_rng,boundary_rng=self.boundary_rng)
                self.update_attempts+=1
                self.record_update_budget()  # durable before any optimizer can step
                result=self.updater.update(b.actor,critic_batch=b.critic,exact_targets=(b.targets,b.mask))
                self.budget.consume()
                result.update(audited_total=self.budget.total,credit_remaining=self.budget.available,
                    episodes=len(c.attempts),exact_target_rows=int(b.mask.sum()),boundary_quota=16,
                    boundary_indices=[list(i) for i in b.indices[-16:]],wall_s=time.perf_counter()-start)
                self.history.append(result); results.append(result)
                self.record_update_budget()
            except BaseException as exc:
                try:self.record_update_budget()
                finally:self.fail(exc)
                raise
        self.admission.verify(); return results
