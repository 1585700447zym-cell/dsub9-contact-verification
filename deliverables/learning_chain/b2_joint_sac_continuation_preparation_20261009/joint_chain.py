"""Whole-episode learning, bounded update credit and durable publication.

Synthetic qualification is a separate capability, never transferable to a
physical training run. Formal construction requires a verified admission.
"""
from copy import deepcopy
from pathlib import Path
import hashlib,math,re,time,os
import numpy as np
from joint_contract import canonical,validate_config,training_cases,SEED,validate_raw_identity
from tools.learning.v4_replay import V4Replay,V4BoundaryIndex
from joint_runtime import V4Updater
from tools.learning.admitted_collection import _write_json,_write_archive

def streams():
    return [np.random.default_rng(np.random.SeedSequence([SEED,i])) for i in (1,2,3)]

def validate_warm(raw,rng,draws):
    held=[0.]*4
    for i,row in enumerate(raw['transitions']):
        if i%50==0:held=rng.uniform(-1.,1.,4).tolist();draws+=1
        request=held if row['action_active'] else [0.]*4
        if row.get('sampling_request')!=held or row['action_log']['raw_action']!=request:raise ValueError('Warmup stream/hold/permission differs')
    if raw['warmup_draws']!=draws:raise ValueError('Warmup draw ledger differs')
    return draws,held

def _audit_raw(raw,config,binding):
    """Recompute identity, physical eligibility, action and reward facts."""
    mode=config['mode'];stage=raw['stage'];index=raw['case_index']
    purpose=binding['purpose']
    if (purpose not in ('synthetic_qualification','bounded_physical_pilot') or
        raw['version']!='v4_training_episode_v1' or raw['scope']!=purpose or
        raw['mode']!=mode or stage not in ('warmup','online') or type(index) is not int or not 0<=index<4 or
        raw['case']!=training_cases()[index] or raw['case_id']!=raw['case']['id'] or
        raw['episode_id']!=stage+'_'+mode+'_'+raw['case_id'] or raw['seed']!=SEED or
        any(raw[k]!=binding[k] for k in ('qualification_sha256','config_sha256')) or
        raw['optimizer_steps_start']!=raw['optimizer_steps'] or raw['fault'] is not None):
        raise ValueError('Unregistered training source, identity or episode boundary')
    validate_raw_identity(raw)
    out=raw['outcome'];rows=raw['transitions']
    if not 0<len(rows)<=14500:raise ValueError('Cycle budget exceeded')
    if rows[-1]['terminated'] is not True or rows[-1]['truncated'] is not False:raise ValueError('Pilot requires natural complete terminal, no truncation')
    V4Replay(mode=mode,capacity=116000)._prepare(rows)
    if purpose=='bounded_physical_pilot':
        from tools.validation.native313_matrix_audit import actual_stop_pass
        from tools.validation.run_contact_candidate_stop import physical_tail_pass
        from tools.validation.verify_admitted_collection import validate_outcome
        stopped=actual_stop_pass(raw['stop_samples'],raw['events'],raw['stop_time'],raw['audit_end_time_s'],.0002)
        stopped=bool(stopped and physical_tail_pass(raw['stop_samples'],raw['audit_end_time_s'],.0002))
        validate_outcome(raw,stopped=stopped)
        if not stopped:raise ValueError('Physical stop audit failed')
        if raw['reference_problems'] or raw['actual_reference_failed']:raise ValueError('Common reference failure')
    from tools.learning.reward import EpisodeReward
    reward=EpisodeReward(.004)
    for i,row in enumerate(rows):
        terms=reward.advance(advance_m=row['advance_m'],dt=row['dt'],force_N=row['cycle_force_N'],torque_G_Nm=row['cycle_torque_G_Nm'])
        terminal=reward.finalize(out['task_outcome']) if i==len(rows)-1 else 0.
        terms['terminal']=terminal;terms['total']+=terminal
        if terms.keys()!=row['reward_terms'].keys() or any(not math.isclose(v,row['reward_terms'][k],abs_tol=1e-12,rel_tol=0) for k,v in terms.items()) or not math.isclose(terms['total'],row['reward'],abs_tol=1e-12,rel_tol=0):
            raise ValueError('Reward differs from independent cycle audit')
        log=row['action_log'];requested=np.asarray(log['raw_action'])
        if requested.shape!=(4,) or not np.isfinite(requested).all() or np.max(np.abs(requested))>1:
            raise ValueError('Invalid requested action')
        expected=log['raw_action'] if row['action_active'] else [0.]*4
        if log['enabled'] is not row['action_active'] or log['experience_action']!=expected or row['action']!=expected:
            raise ValueError('Action permissions/experience mismatch')
        if purpose=='bounded_physical_pilot':
            if len(raw['trace'])!=len(rows)+1 or row['trace_row']!=raw['trace'][i+1] or log!=raw['actions'][i]:
                raise ValueError('Learning row differs from physical transcript')
    if not all(type(out[k]) is bool for k in ('simulation_valid','physical_stopped','valid_for_learning')):
        raise ValueError('Boolean outcome required')
    if out['valid_for_learning']!=(out['simulation_valid'] and out['physical_stopped']):raise ValueError('Eligibility mismatch')
    return out

def audit_raw(raw,config,binding,*,archive_sha256=None):
    from continuation_contract import archive_binding
    return _audit_raw(raw,config,archive_binding(raw,binding,archive_sha256=archive_sha256))

class V4Chain:
    def __init__(self,config,*,output,binding,admission=None):
        validate_config(config);self.config=deepcopy(config);self.mode=config['mode'];self.binding=deepcopy(binding)
        digest=hashlib.sha256(canonical(config).encode()).hexdigest()
        if binding.get('mode')!=self.mode or binding.get('config_sha256')!=digest or not re.fullmatch('[0-9a-f]{64}',binding.get('qualification_sha256','')):
            raise ValueError('Configuration/qualification binding mismatch')
        self.admission=admission
        if binding.get('purpose')!='synthetic_qualification':
            if admission is None or admission.verify(self.mode)!=binding:raise ValueError('Physical learning is not admitted')
        self.output=Path(output).resolve()
        if self.output.exists():raise FileExistsError(self.output)
        self.updater=V4Updater(config);self.origin=self.updater.fingerprints()
        self.replay=V4Replay(mode=self.mode,capacity=config['learning']['replay_capacity']);self.boundary=V4BoundaryIndex(self.mode)
        self.warm_rng,self.replay_rng,self.boundary_rng=streams();self.warm_draws=0;self.held=[0.]*4
        self._audited_warm_rng=streams()[0];self._audited_warm_draws=0
        self.attempts=[];self.history=[];self.update_attempts=0;self.active=False;self.failed=False;self.stop_reason=None
        self.output.mkdir(parents=True)

    def verify(self):
        if self.binding['purpose']=='bounded_physical_pilot' and (self.admission is None or self.admission.verify(self.mode)!=self.binding):
            raise ValueError('Physical admission changed')

    def _healthy(self):
        self.verify()
        if self.failed or self.updater.failed or self.stop_reason:raise RuntimeError('Stopped learning branch')

    def begin(self,stage,index):
        self._healthy()
        sequence=[('warmup',i) for i in range(4)]+[('online',i) for i in range(4)]
        if self.active or len(self.attempts)>=8 or (stage,index)!=sequence[len(self.attempts)]:raise RuntimeError('Episode sequence/active boundary differs')
        if stage=='online' and not self.warm_gate():raise RuntimeError('Insufficient active warmup; no online collection')
        if self.binding['purpose']=='bounded_physical_pilot' and self.updater.counts['critic']!=(500*index if stage=='online' else 0):
            raise RuntimeError('Prior registered updates were not exhausted')
        self.active=True;self.current=(stage,index)

    def warm_action(self,cycle):
        if not self.active or self.current[0]!='warmup':raise RuntimeError('No active warmup')
        if type(cycle) is not int or cycle<0:raise ValueError('Invalid cycle')
        if cycle%50==0:self.held=self.warm_rng.uniform(-1.,1.,4).tolist();self.warm_draws+=1
        return self.held.copy()

    def publish(self,raw):
        if not self.active:raise RuntimeError('No complete episode pending')
        try:
            self.verify()
            if (raw['stage'],raw['case_index'])!=self.current or raw['optimizer_steps']!=self.updater.counts['critic'] or raw['policy_sha256']!=self.updater.fingerprints()['actor']:
                raise ValueError('Policy or pending episode changed')
            out=audit_raw(raw,self.config,self.binding)
            if raw['warmup_draws']!=self.warm_draws:raise ValueError('Live warmup counter differs')
            if raw['stage']=='warmup':
                self._audited_warm_draws,held=validate_warm(raw,self._audited_warm_rng,self._audited_warm_draws)
                if self._audited_warm_rng.bit_generator.state!=self.warm_rng.bit_generator.state or held!=self.held:raise ValueError('Live warmup RNG differs from complete rows')
            folder=self.output/raw['episode_id'];folder.mkdir()
            digest=_write_archive(folder/'episode.json.gz',raw)
            result=self.replay.publish(raw['episode_id'],raw['transitions'],outcome=out,training_admitted=True)
            if result['committed']:self.boundary.add(raw)
            receipt=dict(episode_id=raw['episode_id'],stage=raw['stage'],case_index=raw['case_index'],archive_sha256=digest,
                steps=len(raw['transitions']),optimizer_steps=raw['optimizer_steps'],policy_sha256=raw['policy_sha256'],outcome=deepcopy(out),**result)
            _write_json(folder/'status.json',receipt);self.attempts.append(receipt);self.active=False
            if not result['committed']:self.failed=True;self.stop_reason='INELIGIBLE_EPISODE'
            elif out['task_outcome'] in ('CONTACT_GUARD','MOTION_VIOLATION'):self.stop_reason=out['task_outcome']
            return receipt
        except BaseException:
            self.failed=True;raise

    @property
    def available(self):return min(2000,500*sum(a['stage']=='online' and a['committed']>0 for a in self.attempts))

    def warm_gate(self):
        warm=[a for key,a in self.replay._state.episodes if key.startswith('warmup_')]
        return bool(sum(a['stage']=='warmup' for a in self.attempts)==4 and
            sum(int(a['action_active'].sum()) for a in warm)>=256 and sum(bool(a['action_active'].any()) for a in warm)>=2)

    def update(self,n,*,before_update=None,after_update=None):
        self._healthy()
        if (self.active or type(n) is not int or n<=0 or self.updater.counts['critic']+n>self.available or
            not self.warm_gate()):raise RuntimeError('No qualified update credit/warmup gate')
        result=[]
        for _ in range(n):
            try:
                self.update_attempts+=1
                _write_json(self.output/'update_attempt.json',dict(attempts=self.update_attempts,completed=self.updater.counts['critic']))
                self._append_event('attempt',attempt=self.update_attempts,counts=deepcopy(self.updater.counts))
                if before_update:before_update(self)
                started=time.monotonic();before=self.updater.fingerprints()['actor']
                batch=self.boundary.sample(self.replay,rng=self.replay_rng,boundary_rng=self.boundary_rng)
                stats=self.updater.update(batch.actor,critic_batch=batch.critic,exact_targets=(batch.targets,batch.mask))
                stats.update(actor_before=before,actor_after=self.updater.fingerprints()['actor'],wall_s=time.monotonic()-started,
                    audited_episodes=len(self.attempts),replay_rows=len(self.replay),indices=[list(p) for p in batch.indices],
                    credit_remaining=self.available-self.updater.counts['critic'])
                self.history.append(stats);result.append(stats)
                self._append_event('complete',attempt=self.update_attempts,counts=deepcopy(self.updater.counts),stats=stats)
                if after_update:after_update(self,stats)
            except BaseException as exc:
                self.failed=True
                try:
                    self._append_event('error',attempt=self.update_attempts,counts=deepcopy(self.updater.counts),error=repr(exc))
                    _write_json(self.output/'failure.json',dict(error=repr(exc),counts=self.updater.counts,attempts=self.update_attempts,history=self.history))
                except Exception:pass
                raise
        return result

    def _append_event(self,event,**data):
        with (self.output/'update_journal.jsonl').open('a',encoding='utf8',newline='\n') as f:
            f.write(canonical(dict(event=event,**data))+'\n');f.flush();os.fsync(f.fileno())
