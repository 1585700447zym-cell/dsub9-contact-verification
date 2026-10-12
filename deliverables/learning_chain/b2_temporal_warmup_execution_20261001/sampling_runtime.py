"""Current-cycle context, paired PCG64 streams, and complete sampler restoration."""
from copy import deepcopy
import importlib.util
import numpy as np
from execution_contract import attempts,canonical,DESIGN
spec=importlib.util.spec_from_file_location('sealed_temporal_warmup',DESIGN/'warmup_hold.py')
prepared=importlib.util.module_from_spec(spec);spec.loader.exec_module(prepared)

def require_collection_mode(*,cut_at_end,deterministic):
    if cut_at_end is not False or deterministic is not True:raise ValueError('Complete preflight only; no training or cutoff')
def validate_identity(identity):
    if not any(canonical(identity)==canonical(a) for a in attempts()):raise ValueError('Unregistered paired stream')
def phase_permission(snapshot,expected):
    observed=np.asarray(snapshot.policy_observation,dtype=np.float32);expected=np.asarray(expected,dtype=np.float32)
    phase=snapshot.controller_state['phase'];active=snapshot.residual_enabled
    if (observed.shape!=(120,) or expected.shape!=(120,) or not np.isfinite(observed).all() or
            (np.abs(observed)>10).any() or not np.array_equal(observed,expected) or type(active) is not bool or phase not in prepared.PHASES):
        raise ValueError('Current cached observation/context differs')
    onehot=[float(phase==p) for p in prepared.PHASES]
    if observed[53:58].tolist()!=onehot or observed[76]!=float(active):raise ValueError('Phase or permission differs from observation')
    return phase,active

class Schedule:
    def __init__(self,identity,live_check):
        validate_identity(identity);self.identity=deepcopy(identity);self.live_check=live_check
        self.rng=np.random.Generator(np.random.PCG64(np.random.SeedSequence([2026092716,1,identity['case_index']])))
        self.initial=deepcopy(self.rng.bit_generator.state)
        self.sampler=prepared.WarmupHold(self.draw,hold_cycles=identity['hold_cycles']);self.records=[]
    def draw(self):return self.rng.uniform(-1.,1.,4).astype(np.float32)
    def act(self,snapshot,expected):
        self.live_check();phase,active=phase_permission(snapshot,expected)
        record=self.sampler.next(snapshot.cycle_id,phase,active);self.records.append(deepcopy(record));return record['action'].copy()
    def capture(self):
        return dict(version='temporal_preflight_sampler_state_v1',identity=deepcopy(self.identity),
            rng_initial=deepcopy(self.initial),rng_final=deepcopy(self.rng.bit_generator.state),sampler=self.sampler.snapshot())
    @classmethod
    def restore(cls,state,live_check):
        if not isinstance(state,dict) or set(state)!= {'version','identity','rng_initial','rng_final','sampler'} or state['version']!='temporal_preflight_sampler_state_v1':
            raise ValueError('Complete registered sampler+RNG state required')
        new=cls(state['identity'],live_check)
        if canonical(new.initial)!=canonical(state['rng_initial']):raise ValueError('Paired initial RNG differs')
        restored=prepared.WarmupHold.restore(new.draw,state['sampler'],expected_hold_cycles=new.identity['hold_cycles'])
        expected=np.random.PCG64();expected.state=deepcopy(new.initial);expected.advance(4*restored.draw_count)
        if canonical(expected.state)!=canonical(state['rng_final']):raise ValueError('RNG consumption differs from durable sampler count')
        new.rng.bit_generator.state=deepcopy(state['rng_final']);new.sampler=restored;return new

class ContextPolicy:
    def __init__(self,session,schedule):self.session=session;self.schedule=schedule
    def predict(self,observation,deterministic=True):
        if deterministic is not True:raise ValueError('Registered warmup preflight interface required')
        before=self.session.prepare_cycle()  # Cached once-per-control-cycle B2 update.
        return np.asarray(self.schedule.act(before,observation),dtype=np.float32),None

def audit_sampling(raw):
    identity=raw['preflight_identity'];validate_identity(identity)
    schedule=Schedule(identity,lambda:None);rows=raw['transitions'];records=raw['sampling_records']
    if len(rows)!=len(records):raise ValueError('Sampling transcript incomplete')
    for i,(row,record) in enumerate(zip(rows,records)):
        phase=record['policy_phase']
        class Snapshot:pass
        snapshot=Snapshot();snapshot.cycle_id=i;snapshot.controller_state={'phase':phase}
        snapshot.residual_enabled=row['action_active'];snapshot.policy_observation=row['observation']
        action=schedule.act(snapshot,row['observation'])
        if canonical(schedule.records[-1])!=canonical(record) or action!=row['action_log']['raw_action'] or row['action']!=(action if row['action_active'] else [0.]*4):
            raise ValueError('Action, permission, block or RNG transcript differs')
    if canonical(schedule.capture())!=canonical(raw['sampling_final']):raise ValueError('Final complete sampling state differs')
    restored=Schedule.restore(raw['sampling_final'],lambda:None)
    if canonical(restored.capture())!=canonical(schedule.capture()):raise ValueError('Separate sampler restoration differs')
    return dict(complete_sampling_state_restored=True,cycles=len(rows),draw_count=schedule.sampler.draw_count,
        network_calls=0,training_batches=0)
