"""Versioned, audited, full-state checkpoints for the bounded cycle only."""
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
from .admission import canonical,digest
from .audited_replay import AuditedReplay
from .boundary_targets import BoundaryIndex
from .bounded_contact import (BoundedCollection,BoundedUpdater,BalancedSampler,EpisodeBudget,
                              SEED,validate_case,guard_clear)
from .sac_checkpoint import _same,_integer,_tensor,_optimizer,_rng,_replay_state,_audit_physics,_flush_write
from .episode_rules import rules_for, STRICT


def capture(chain):
    c=chain.collector
    if (chain.failed or chain.updater.failed or c.active or c._blocked or c._pending is not None or
        c._status_pending or c.session is not None or getattr(c,'buffer',None) is not None):
        raise RuntimeError('Healthy audited boundary required')
    record=chain.admission.verify(); archives={}
    for receipt in c.attempts:
        folder=c.output/receipt['episode_id']
        if json.loads((folder/'status.json').read_text(encoding='utf-8'))!=receipt:
            raise ValueError('Receipt not durably saved')
        archives[receipt['episode_id']]=(folder/'episode.json.gz').read_bytes()
    return deepcopy(dict(version=rules_for(chain.admission).checkpoint_version,binding=dict(
        qualification_sha256=chain.admission.expected_digest,record=record),updater=chain.updater._snapshot(),
        replay=_replay_state(chain.replay),archives=archives,attempts=c.attempts,history=chain.history,
        budget=dict(total=chain.budget.total,completed=chain.budget.completed,receipts=chain.budget._receipts),
        sampler_count=chain.sampler.count,update_attempts=chain.update_attempts,rng=dict(warmup=chain.warmup.rng.bit_generator.state,
        replay=chain.replay_rng.bit_generator.state,boundary=chain.boundary_rng.bit_generator.state)))


def validate_state(state,admission):
    record=admission.verify()
    rules=rules_for(admission)
    if (state.get('version')!=rules.checkpoint_version or not _same(state.get('binding'),dict(
        qualification_sha256=admission.expected_digest,record=record))):
        raise ValueError('Checkpoint qualification differs')
    attempts=state['attempts']; count=_integer(state['sampler_count'],0,12)
    if count!=len(attempts) or set(state['archives'])!={f'train_{i:02d}' for i in range(count)}:
        raise ValueError('Attempt/archive/sampler mismatch')
    replay=AuditedReplay(capacity=156000); budget=EpisodeBudget(rules=rules)
    sampler=BalancedSampler(); index=BoundaryIndex(rules=rules)
    totals=[0]; lengths=[]
    for i,receipt in enumerate(attempts):
        key=f'train_{i:02d}'
        if receipt['episode_id']!=key: raise ValueError('Episode order changed')
        compressed=state['archives'][key]
        if not isinstance(compressed,bytes) or hashlib.sha256(compressed).hexdigest()!=receipt['archive_sha256']:
            raise ValueError('Archive digest differs')
        raw=json.loads(gzip.decompress(compressed)); validate_case(raw['case'],training=True)
        if (raw['episode_id']!=key or raw['case']!=sampler.next_case() or not rules.accepts(raw) or
            not rules.receipt_valid(receipt) or raw['qualification_sha256']!=admission.expected_digest or
            raw['seed']!=SEED or raw['sampling_mode']!=('uniform_warmup' if i<4 else 'sac_policy') or
            raw['optimizer_steps']!=max(0,i-3)*500):
            raise ValueError('Unqualified or unbalanced archived episode')
        if rules is not STRICT and raw.get('learning_eligibility')!=receipt.get('learning_eligibility'):
            raise ValueError('Eligibility receipt differs from raw archive')
        for name in ('episode_id','case','seed','qualification_sha256','optimizer_steps','optimizer_steps_start',
                     'policy_sha256','sampling_mode','audit_end_time_s'):
            if not _same(raw[name],receipt[name]): raise ValueError('Raw receipt mismatch: '+name)
        if raw['optimizer_steps_start']!=raw['optimizer_steps']: raise ValueError('In-episode learning')
        _audit_physics(raw)
        for name in ('simulation_valid','physical_stopped','valid_for_learning','task_outcome'):
            if raw['outcome'][name]!=receipt[name]: raise ValueError('Outcome receipt mismatch')
        result=replay.publish(key,raw['transitions'],outcome=raw['outcome'],training_admitted=True)
        if any(type(receipt[k]) is not int or result[k]!=receipt[k] for k in result):
            raise ValueError('Publication counts mismatch')
        if receipt['steps']!=len(raw['transitions']): raise ValueError('Cycle count differs')
        while budget.available: budget.consume()
        budget.record(receipt); index.add(raw); lengths.append(len(raw['transitions'])); totals.append(budget.total)
        if budget.stop_reason: raise ValueError('Frequency-stopped run is not a resumable healthy checkpoint')
    if not _same(_replay_state(replay),state['replay']): raise ValueError('Replay differs from raw archives')
    saved=state['updater']; counts=saved['counts']
    if set(counts)!={'critic','actor','temperature','target'}: raise ValueError('Missing update count')
    for v in counts.values():_integer(v,0,4500)
    completed=_integer(state['budget']['completed'],0,4500)
    if _integer(state['update_attempts'],0,4500)!=completed:
        raise ValueError('Failed or interrupted update cannot be restored as healthy')
    if (counts['critic']!=completed or counts['target']!=completed or counts['actor']!=counts['temperature'] or
        counts['actor']>completed or completed<budget.completed or completed>budget.completed+budget.available):
        raise ValueError('Invalid earned update count')
    budget.completed=completed
    if not _same(state['budget'],dict(total=budget.total,completed=completed,receipts=budget._receipts)):
        raise ValueError('Update ledger changed')
    history=state['history'];canonical(history)
    if len(history)!=completed: raise ValueError('Missing update history')
    expected_replay=np.random.Generator(np.random.PCG64(np.random.SeedSequence([SEED,2])))
    expected_boundary=np.random.Generator(np.random.PCG64(np.random.SeedSequence([SEED,3])))
    for i,row in enumerate(history,1):
        n=4+(i-1)//500
        if (n>count or row['episodes']!=n or row['audited_total']!=totals[n] or row['critic_batches']!=i or
            row['credit_remaining']!=(n-3)*500-i or row['batch_rows']!=256 or row['boundary_quota']!=16):
            raise ValueError('History credit/order mismatch')
        _integer(row['active_rows'],0,256)
        expected_replay.integers(0,totals[n],size=256)
        candidates=[(k,index.entries[k][2]) for k in list(index.entries)[:n] if index.entries[k][2] is not None]
        if not candidates: raise ValueError('No historical boundary')
        chosen=[list(candidates[int(j)]) for j in expected_boundary.integers(0,len(candidates),size=16)]
        if row['boundary_indices']!=chosen: raise ValueError('Boundary draw history differs')
    if counts['actor']!=sum(r['active_rows']>0 for r in history): raise ValueError('Actor permission count mismatch')
    expected_warmup=np.random.Generator(np.random.PCG64(np.random.SeedSequence([SEED,1])))
    expected_warmup.bit_generator.advance(4*sum(lengths[:4]))
    for key,expected in (('warmup',expected_warmup),('replay',expected_replay),('boundary',expected_boundary)):
        if not _same(state['rng'][key],expected.bit_generator.state): raise ValueError('RNG accounting differs: '+key)
    updater=getattr(admission,'updater_type',BoundedUpdater)(record['config']); reference=updater._snapshot()
    if saved.keys()!=reference.keys() or saved['policy'].keys()!=reference['policy'].keys():
        raise ValueError('Missing policy state')
    for key in reference['policy']:_tensor(saved['policy'][key],reference['policy'][key])
    _tensor(saved['alpha'],reference['alpha']);_tensor(saved['rng'],reference['rng'])
    torch.Generator().set_state(saved['rng'])
    for key,opt in zip(('critic','actor','temperature'),updater._optimizers()):_optimizer(saved[key],opt,counts[key])
    updater._restore(deepcopy(saved));updater._finite_state()
    return updater,replay,budget,sampler,index,_rng(state['rng']['warmup']),_rng(state['rng']['replay']),_rng(state['rng']['boundary'])


def save_checkpoint(chain,output):
    output=Path(output).resolve()
    if output.exists():raise FileExistsError(output)
    state=capture(chain);validate_state(state,chain.admission)
    output.parent.mkdir(parents=True,exist_ok=True)
    staging=output.with_name(output.name+'.pending-'+uuid.uuid4().hex);staging.mkdir()
    with (staging/'state.pt').open('xb') as stream:
        torch.save(state,stream);stream.flush();os.fsync(stream.fileno())
    _flush_write(staging/'manifest.json',canonical(dict(version='bounded_checkpoint_manifest_v2',state_sha256=digest(staging/'state.pt'))))
    chain.admission.verify();os.rename(staging,output)
    return digest(output/'manifest.json')


def read_checkpoint(path,*,expected_digest,admission):
    path=Path(path);data=(path/'manifest.json').read_bytes()
    if hashlib.sha256(data).hexdigest()!=expected_digest:raise ValueError('Checkpoint pin differs')
    manifest=json.loads(data);payload=(path/'state.pt').read_bytes()
    if manifest['version']!='bounded_checkpoint_manifest_v2' or hashlib.sha256(payload).hexdigest()!=manifest['state_sha256']:
        raise ValueError('Checkpoint payload differs')
    state=torch.load(io.BytesIO(payload),map_location='cpu',weights_only=True)
    return state,validate_state(state,admission)


def load_checkpoint(path,*,expected_digest,admission,output):
    output=Path(output)
    if output.exists():raise FileExistsError(output)
    state,components=read_checkpoint(path,expected_digest=expected_digest,admission=admission)
    chain=BoundedCollection(admission=admission,output=output)
    (chain.updater,chain.replay,chain.budget,chain.sampler,chain.index,
     chain.warmup.rng,chain.replay_rng,chain.boundary_rng)=components
    chain.collector.updater=chain.updater;chain.collector.replay=chain.replay
    chain.collector.attempts=deepcopy(state['attempts']);chain.history=deepcopy(state['history'])
    chain.update_attempts=state['update_attempts']
    for receipt in chain.collector.attempts:
        folder=output/receipt['episode_id'];folder.mkdir()
        _flush_write(folder/'episode.json.gz',state['archives'][receipt['episode_id']])
        _flush_write(folder/'status.json',canonical(receipt))
    admission.verify();return chain
