"""Fixed audited data, exact draw order, complete branch state; no launch on import."""
from copy import deepcopy
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import time
import uuid
import numpy as np
import torch
from .actor_lr_contract import (ORIGIN,ORIGIN_PIN,execution_config,branch_binding,digest,canonical,verify_files)
from .actor_lr_origin import fork_origin,read_pinned_state
from .audited_replay import AuditedReplay,_State,ReplayBatch
from .boundary_targets import BoundaryIndex,gather
from .episode_rules import FORCE_ONLY
from .sac_update import SACUpdater
from .sac_checkpoint import _same,_tensor,_optimizer,_rng,_flush_write


class ComparisonUpdater(SACUpdater):
    from .actor_lr_contract import validate_execution_config
    config_validator=staticmethod(validate_execution_config)


def read_origin():
    data=(ORIGIN/'manifest.json').read_bytes()
    if hashlib.sha256(data).hexdigest()!=ORIGIN_PIN:raise ValueError('Common origin pin differs')
    manifest=json.loads(data)
    if manifest['version']!='actor_lr_origin_manifest_v1':raise ValueError('Unknown common origin')
    source=(ORIGIN/'source_sha256.json').read_bytes()
    if hashlib.sha256(source).hexdigest()!=manifest['source_manifest_sha256']:raise ValueError('Origin source pin differs')
    verify_files(json.loads(source));verify_files(manifest['archived_inputs_sha256'])
    payload=(ORIGIN/'state.pt').read_bytes();draws=(ORIGIN/'draw_plan.json.gz').read_bytes()
    if (hashlib.sha256(payload).hexdigest()!=manifest['state_sha256'] or
        hashlib.sha256(draws).hexdigest()!=manifest['draw_plan_sha256']):raise ValueError('Origin payload or draws differ')
    state=torch.load(io.BytesIO(payload),map_location='cpu',weights_only=True)
    plan=json.loads(gzip.decompress(draws))
    # The origin is an immutable preparation artifact; only separate execution
    # binding and authorization allow its future use in an execution worker.
    fork_origin(state,'A',manifest['source_manifest_sha256'])
    if plan['version']!='actor_lr_fixed_draw_plan_v1' or len(plan['batches'])!=500:
        raise ValueError('Exact 500 fixed draws required')
    return state,plan


def components(state):
    replay=AuditedReplay(capacity=state['replay']['capacity']);episodes=[]
    for key,arrays in state['replay']['episodes']:
        values={k:v.numpy().copy() for k,v in arrays.items()}
        for array in values.values():array.setflags(write=False)
        episodes.append((key,values))
    replay._state=_State(tuple(episodes),frozenset(state['replay']['seen']),state['replay']['size'])
    # This index was fully re-audited when origin_v2 was sealed. read_origin
    # pins those same bytes; checkpoint validation compares it in full.
    index=BoundaryIndex(rules=FORCE_ONLY)
    index.entries={key:(entry['targets'].numpy().copy(),entry['mask'].numpy().copy(),entry['boundary'])
        for key,entry in state['boundary_index'].items()}
    return replay,index


def inactive_batch(batch):
    values={k:getattr(batch,k).clone() for k in ReplayBatch.__dataclass_fields__}
    for key in ('actions','action_active','next_action_active'):values[key].zero_()
    return ReplayBatch(**values)


class OfflineBranch:
    def __init__(self,origin,plan,branch,candidate_pin,authorization_pin):
        self.branch=branch;self.config=execution_config(branch);self.origin=deepcopy(origin);self.plan=deepcopy(plan)
        self.candidate_pin=candidate_pin;self.authorization_pin=authorization_pin
        self.state=fork_origin(origin,branch,json.loads((ORIGIN/'manifest.json').read_bytes())['source_manifest_sha256'])
        self.state.update(version='actor_lr_execution_checkpoint_v1',
            comparison_binding=branch_binding(self.config,candidate_pin,authorization_pin))
        self.updater=ComparisonUpdater(self.config);self.updater._restore(deepcopy(self.state['updater']))
        self.replay,self.index=components(origin)
        self.replay_rng=_rng(origin['rng']['replay']);self.boundary_rng=_rng(origin['rng']['boundary'])
        self.failed=False

    def next_batch(self):
        n=self.state['update_attempts']
        if self.failed or n>=500:raise RuntimeError('Healthy fixed-data update boundary required')
        row=self.plan['batches'][n]
        batch=self.index.sample(self.replay,rng=self.replay_rng,boundary_rng=self.boundary_rng)
        if [list(x) for x in batch.indices]!=row['critic_indices']:raise ValueError('Fixed critic draw mismatch')
        lengths=[len(a['rewards']) for _,a in self.replay._state.episodes];ends=np.cumsum(lengths);starts=np.r_[0,ends[:-1]]
        base=[(self.replay._state.episodes[int(o)][0],int(i-starts[o])) for o,i in
            zip(np.searchsorted(ends,row['actor_flat_indices'],side='right'),row['actor_flat_indices'])]
        expected=gather(self.replay._state.episodes,base)
        if any(not torch.equal(getattr(batch.actor,k),getattr(expected,k)) for k in ReplayBatch.__dataclass_fields__):
            raise ValueError('Fixed actor draw mismatch')
        return batch

    def update_one(self,ledger):
        if self.failed or self.updater.failed:raise RuntimeError('Failed branch cannot retry')
        n=self.state['update_attempts']
        # Persist attempted cost before consuming a stream or performing a step.
        ledger.assert_binding(self.candidate_pin,self.authorization_pin,self.branch,n)
        token=ledger.reserve('formal',self.branch,f'batch_{n:03d}')
        started=time.perf_counter()
        try:
            b=self.next_batch();self.state['update_attempts']=n+1
            result=self.updater.update(b.actor,critic_batch=b.critic,exact_targets=(b.targets,b.mask))
            self.state['budget']['completed']=n+1
            result.update(audited_total=22766,credit_remaining=499-n,episodes=4,
                exact_target_rows=int(b.mask.sum()),boundary_quota=16,
                boundary_indices=[list(i) for i in b.indices[-16:]],wall_s=time.perf_counter()-started)
            self.state['history'].append(deepcopy(result))
            ledger.finish(token,dict(completed=True,critic_batches=n+1,active_rows=result['active_rows']))
            return result
        except BaseException as exc:
            self.failed=True;ledger.fail(repr(exc));raise

    def capture(self):
        if self.failed or self.updater.failed:raise RuntimeError('Failed branch has no healthy checkpoint')
        result=deepcopy(self.state);result['updater']=self.updater._snapshot()
        result['rng'].update(replay=deepcopy(self.replay_rng.bit_generator.state),boundary=deepcopy(self.boundary_rng.bit_generator.state))
        return result


def validate_state(state,origin,plan,branch,candidate_pin,authorization_pin,*,formal_only=True):
    """Validate every retained component before restoring a private updater."""
    config=execution_config(branch)
    if (state.get('version')!='actor_lr_execution_checkpoint_v1' or
        not _same(state.get('comparison_binding'),branch_binding(config,candidate_pin,authorization_pin)) or
        state.keys()!=set(origin)|{'comparison_binding'}):raise ValueError('Branch checkpoint binding or schema differs')
    for key in ('binding','replay','archives','attempts','sampler_count','boundary_index'):
        if not _same(state[key],origin[key]):raise ValueError('Immutable origin differs: '+key)
    n=state['budget']['completed'];saved=state['updater'];counts=saved['counts'];history=state['history']
    if type(n) is not int or not 0<=n<=500 or (formal_only and n!=500):raise ValueError('Fixed completed 500-update checkpoint required')
    budget=deepcopy(origin['budget']);budget['completed']=n
    if (not _same(state['budget'],budget) or type(state['update_attempts']) is not int or state['update_attempts']!=n or
        set(counts)!={'actor','critic','temperature','target'} or any(type(v) is not int or not 0<=v<=500 for v in counts.values()) or
        counts['critic']!=n or counts['target']!=n or counts['actor']!=counts['temperature'] or counts['actor']>n or
        not isinstance(history,list) or len(history)!=n):raise ValueError('Attempt, credit or learning counters differ')
    canonical(history)
    replay_rng=_rng(origin['rng']['replay']);boundary_rng=_rng(origin['rng']['boundary'])
    arrays=[a for _,a in origin['replay']['episodes']]
    active=torch.cat([a['action_active'] for a in arrays])[:,0]
    actor_count=0
    for i,row in enumerate(history):
        expected=plan['batches'][i];replay_rng.integers(0,22766,size=256);boundary_rng.integers(0,4,size=16)
        active_rows=int(active[expected['actor_flat_indices']].sum());actor_count+=active_rows>0
        if (row['critic_batches']!=i+1 or row['episodes']!=4 or row['audited_total']!=22766 or
            row['credit_remaining']!=499-i or row['batch_rows']!=256 or row['active_rows']!=active_rows or
            row['boundary_quota']!=16 or row['boundary_indices']!=expected['critic_indices'][-16:]):
            raise ValueError('Fixed draw history or permission count differs')
    if counts['actor']!=actor_count:raise ValueError('Actor permission accounting differs')
    expected_rng=dict(warmup=origin['rng']['warmup'],replay=replay_rng.bit_generator.state,boundary=boundary_rng.bit_generator.state)
    if not _same(state['rng'],expected_rng):raise ValueError('Complete RNG accounting differs')
    updater=ComparisonUpdater(config);reference=updater._snapshot()
    if saved.keys()!=reference.keys() or saved['policy'].keys()!=reference['policy'].keys():raise ValueError('Missing learned state')
    for key in reference['policy']:_tensor(saved['policy'][key],reference['policy'][key])
    _tensor(saved['alpha'],reference['alpha']);_tensor(saved['rng'],reference['rng']);torch.Generator().set_state(saved['rng'])
    for key,opt in zip(('critic','actor','temperature'),updater._optimizers()):_optimizer(saved[key],opt,counts[key])
    if not n:
        initial=fork_origin(origin,branch,json.loads((ORIGIN/'manifest.json').read_bytes())['source_manifest_sha256'])['updater']
        if not _same(saved,initial):raise ValueError('Zero-update weights or RNG differ')
    updater._restore(deepcopy(saved));updater._finite_state();return updater


def save_checkpoint(engine,output):
    output=Path(output)
    if output.exists():raise FileExistsError(output)
    state=engine.capture()
    validate_state(state,engine.origin,engine.plan,engine.branch,engine.candidate_pin,engine.authorization_pin)
    output.parent.mkdir(parents=True,exist_ok=True);staging=output.with_name(output.name+'.pending-'+uuid.uuid4().hex);staging.mkdir()
    with (staging/'state.pt').open('xb') as stream:torch.save(state,stream);stream.flush();os.fsync(stream.fileno())
    manifest=dict(version='actor_lr_execution_manifest_v1',state_sha256=digest(staging/'state.pt'),
        comparison_binding=state['comparison_binding'])
    _flush_write(staging/'manifest.json',canonical(manifest));os.rename(staging,output)
    return digest(output/'manifest.json')


def load_checkpoint(path,pin,origin,plan,branch,candidate_pin,authorization_pin):
    data=(Path(path)/'manifest.json').read_bytes()
    if hashlib.sha256(data).hexdigest()!=pin:raise ValueError('Execution checkpoint pin differs')
    manifest=json.loads(data);payload=(Path(path)/'state.pt').read_bytes()
    if (manifest.get('version')!='actor_lr_execution_manifest_v1' or
        not _same(manifest.get('comparison_binding'),branch_binding(execution_config(branch),candidate_pin,authorization_pin)) or
        hashlib.sha256(payload).hexdigest()!=manifest['state_sha256']):raise ValueError('Execution checkpoint payload or branch differs')
    state=torch.load(io.BytesIO(payload),map_location='cpu',weights_only=True)
    updater=validate_state(state,origin,plan,branch,candidate_pin,authorization_pin)
    return state,updater


def reproduction_fields_equal(actual,historical):
    # Branch identity and qualification are new. Every physical data, learned
    # tensor, Adam group/moment, credit, counter and random stream is compared.
    keys=('updater','replay','archives','attempts','budget','sampler_count','update_attempts','rng')
    if any(not _same(actual[k],historical[k]) for k in keys):return False
    strip=lambda rows:[{k:v for k,v in r.items() if k!='wall_s'} for r in rows]
    return _same(strip(actual['history']),strip(historical['history']))


def verify_a_reproduction(engine):
    manifest=json.loads((ORIGIN/'manifest.json').read_bytes())
    from .actor_lr_contract import OLD,ROOT
    rel=(OLD/'run/training/checkpoints/train_03/manifest.json').relative_to(ROOT).as_posix()
    historical=read_pinned_state(OLD/'run/training/checkpoints/train_03',manifest['archived_inputs_sha256'][rel])
    actual=engine.capture()
    if actual['budget']['completed']!=500 or not reproduction_fields_equal(actual,historical):
        raise ValueError('Exact A learning reproduction failed; B branch refused')
    if not _same({k:actual['rng'][k] for k in ('replay','boundary')},engine.plan['final_rng']):raise ValueError('Final fixed RNG differs')
    return dict(learning_exact=True,completed_batches=500,excluded_fields=['version','comparison_binding','binding','history.wall_s'],
        historical_manifest_sha256=manifest['archived_inputs_sha256'][rel])
