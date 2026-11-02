"""Audited terminal-tail labels and critic-only boundary sampling.

Raw replay, observation, dt and termination semantics are never rewritten.
Labels are trajectory return samples, not claims about conditional expectation.
"""
from dataclasses import dataclass
import numpy as np
import torch
from .audited_replay import AuditedReplay, ReplayBatch
from .contact_contract import guard_clear


def exact_tail(raw, *, rules=None):
    if not (guard_clear(raw) if rules is None else rules.accepts(raw)):
        raise ValueError('Eligible audited episode required')
    rows=raw['transitions']
    prepared=AuditedReplay(capacity=max(1,len(rows)))._prepare(rows)
    targets=np.zeros(len(rows),dtype=np.float64)
    mask=np.zeros(len(rows),dtype=bool)
    if rows[-1]['truncated']: return targets,mask,None
    if rows[-1]['next_action_active']: raise ValueError('Terminal next state cannot select actions')
    active=np.flatnonzero(prepared['action_active'][:,0])
    boundary=int(active[-1]) if len(active) else None
    start=boundary if boundary is not None else 0
    value=0.
    for i in range(len(rows)-1,start-1,-1):
        value=float(rows[i]['reward'])+float(rows[i]['discount'])*value
        targets[i]=value; mask[i]=True
    if not np.isfinite(targets).all(): raise ValueError('Nonfinite tail target')
    return targets,mask,boundary


@dataclass(frozen=True)
class LearningBatch:
    actor: ReplayBatch
    critic: ReplayBatch
    targets: torch.Tensor
    mask: torch.Tensor
    indices: tuple


def gather(episodes, indices):
    arrays=dict(episodes)
    return ReplayBatch(**{name:torch.tensor(np.stack([arrays[key][name][i] for key,i in indices]))
                          for name in ReplayBatch.__dataclass_fields__})


class BoundaryIndex:
    def __init__(self, *, rules=None): self.entries={}; self.rules=rules

    def add(self,raw):
        key=raw['episode_id']
        if key in self.entries: raise ValueError('Duplicate boundary episode')
        self.entries[key]=exact_tail(raw,rules=self.rules)

    def sample(self,replay,*,rng,boundary_rng):
        episodes=replay._state.episodes
        keys=[key for key,_ in episodes]
        if not keys or any(key not in self.entries for key in keys):
            raise ValueError('Replay lacks audited boundary index')
        for key,a in episodes:
            if len(a['rewards'])!=len(self.entries[key][0]): raise ValueError('Boundary/replay length mismatch')
        candidates=[(key,self.entries[key][2]) for key in keys if self.entries[key][2] is not None]
        if not candidates: raise ValueError('No legal decision boundary')
        ends=np.cumsum([len(a['rewards']) for _,a in episodes]); starts=np.r_[0,ends[:-1]]
        uniform=rng.integers(0,len(replay),size=256)
        owners=np.searchsorted(ends,uniform,side='right')
        base=tuple((keys[o],int(i-starts[o])) for o,i in zip(owners,uniform))
        boundary=tuple(candidates[int(i)] for i in boundary_rng.integers(0,len(candidates),size=16))
        selected=base[:240]+boundary
        targets=torch.tensor([[self.entries[k][0][i]] for k,i in selected],dtype=torch.float32)
        mask=torch.tensor([[self.entries[k][1][i]] for k,i in selected],dtype=torch.bool)
        return LearningBatch(gather(episodes,base),gather(episodes,selected),targets,mask,selected)
