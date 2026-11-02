"""Whole-episode 137D replay and terminal boundary labels; caller owns admission."""
import numpy as np
from .audited_replay import AuditedReplay,ReplayBatch,_boolean,_number
from .action import normalized_action
from .episode_buffer import _archive
from .v4_pilot_contract import permission
from .boundary_targets import BoundaryIndex
import math

class V4Replay(AuditedReplay):
    def __init__(self,*,mode,capacity):
        if mode not in ('F50','S50'):raise ValueError('Explicit pilot mode required')
        self.mode=mode;super().__init__(capacity=capacity)

    def _prepare(self,rows):
        if not rows or len(rows)>self.capacity:raise ValueError('Complete nonempty episode must fit')
        arrays={name:[] for name in ReplayBatch.__dataclass_fields__};previous=None
        for i,row in enumerate(rows):
            if not isinstance(row,dict) or not _archive(row)[1]:raise ValueError('Nonfinite archive')
            flags={k:_boolean(row[k]) for k in ('terminated','truncated','action_active','next_action_active')}
            if flags['terminated'] and flags['truncated'] or (flags['terminated'] or flags['truncated'])!=(i==len(rows)-1):
                raise ValueError('Exactly one final boundary required')
            obs,nxt=[np.asarray(row[k]) for k in ('observation','next_observation')]
            if permission(obs,self.mode)!=flags['action_active'] or permission(nxt,self.mode)!=flags['next_action_active']:
                raise ValueError('Flags differ from observations')
            if previous is not None and (not np.array_equal(previous[0],obs) or previous[1]!=flags['action_active']):
                raise ValueError('Discontinuous episode')
            action=normalized_action(row['action'])
            if not flags['action_active'] and np.any(action):raise ValueError('Inactive experience must be zero')
            dt,g,r=[_number(row[k]) for k in ('dt','discount','reward')]
            if dt<=0 or not 0<g<=1 or not math.isclose(g,math.exp(-dt/10),rel_tol=0,abs_tol=1e-12):
                raise ValueError('Physical-time discount mismatch')
            values=dict(observations=obs,next_observations=nxt,actions=action,rewards=[r],discounts=[g],dt=[dt],
                **{k:[v] for k,v in flags.items()})
            for k,v in values.items():arrays[k].append(v)
            previous=nxt,flags['next_action_active']
        prepared={}
        for k,v in arrays.items():
            a=np.asarray(v,dtype=np.bool_ if k in flags else np.float32)
            if not np.isfinite(a).all():raise ValueError('Unrepresentable episode tensor')
            a.setflags(write=False);prepared[k]=a
        return prepared

class V4BoundaryIndex(BoundaryIndex):
    def __init__(self,mode):super().__init__();self.mode=mode
    def add(self,raw):
        key=raw['episode_id'];out=raw['outcome']
        if key in self.entries or not all(out.get(k) is True for k in ('simulation_valid','physical_stopped','valid_for_learning')):
            raise ValueError('New eligible complete episode required')
        rows=raw['transitions'];a=V4Replay(mode=self.mode,capacity=max(1,len(rows)))._prepare(rows)
        targets=np.zeros(len(rows),dtype=float);mask=np.zeros(len(rows),dtype=bool)
        if rows[-1]['truncated']:self.entries[key]=targets,mask,None;return
        if rows[-1]['next_action_active']:raise ValueError('Terminal next action active')
        active=np.flatnonzero(a['action_active'][:,0]);boundary=int(active[-1]) if len(active) else None
        value=0.
        for i in range(len(rows)-1,(boundary if boundary is not None else 0)-1,-1):
            value=float(rows[i]['reward'])+float(rows[i]['discount'])*value;targets[i]=value;mask[i]=True
        if not np.isfinite(targets).all():raise ValueError('Nonfinite exact tail')
        self.entries[key]=targets,mask,boundary
