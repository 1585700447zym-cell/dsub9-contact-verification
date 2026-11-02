"""Registered 137D pilot settings and schema-derived permissions; no admission."""
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
import gzip,json,hashlib
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
DELIVERY=ROOT/'deliverables/paper_comparison/v4_learning_requalification_20261006'
PRIOR=ROOT/'deliverables/paper_comparison/v4_continuation_20261006'
PLAN='docs/superpowers/plans/2026-10-06-v4-learning-requalification.md'
SEED=2026092716
WIDTH=137

def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))

@lru_cache(maxsize=1)
def _schema():
    if sha(PRIOR/'delivery_manifest.json')!='536a599cd5b8baaab8fbb8951f8b1557a6eb40bc2d215f12603103d0a07a4673':raise ValueError('PC-03 seal changed')
    p=PRIOR/'run/F50_boundary_y_neg_150.json.gz'
    if sha(p)!='c07bf6c39259fe42cb2ad1faaf1898749d61bcbcf6756d4f9ac0da8476191f30':raise ValueError('Schema source changed')
    s=json.loads(gzip.decompress(p.read_bytes()))['observation_schema']
    offset=0;names=set()
    for f in s:
        if f['start']!=offset or f['width']<1 or f['name'] in names:raise ValueError('Noncontiguous schema')
        names.add(f['name']);offset+=f['width']
    if offset!=WIDTH:raise ValueError('Unexpected observation version')
    return s

def field_slices():return {f['name']:slice(f['start'],f['start']+f['width']) for f in _schema()}

def training_cases():
    return deepcopy(read(ROOT/'deliverables/paper_comparison/protocol_v4_20261004/protocol.json')['common']['cases'][:4])

def learning_config(mode):
    if mode not in ('F50','S50'):raise ValueError('Registered F50 or S50 required')
    return dict(version='v4_learning_pilot_v1',mode=mode,observation_version='residual_reference_whitelist_v4',
        schema=deepcopy(_schema()),width=WIDTH,action_scale=[.00005,.00005,.0005,.0005],
        reference_filter='residual_reference_continuation_v2',
        learning=dict(learning_rate=.0003,actor_learning_rate=.0003,batch_size=256,replay_capacity=116000,
            network=[256,256],seed=SEED,torch_threads=1,device='cpu',entropy_initial=.01,target_entropy=-4.,tau=.005,
            max_gradient_batches=2000,critic_boundary_rows=16,exact_terminal_tail=True),
        warmup=dict(episodes=4,hold_cycles=50,min_active_rows=256,min_active_cases=2),
        online=dict(episodes=4,batches_per_episode=500),discount_time_constant_s=10.)

def validate_config(c):
    if not isinstance(c,dict) or canonical(c)!=canonical(learning_config(c.get('mode'))):raise ValueError('Unregistered 137D pilot configuration')

def permissions(observations,mode):
    if mode not in ('F50','S50'):raise ValueError('Registered mode required')
    o=np.asarray(observations)
    if o.ndim!=2 or o.shape[1]!=WIDTH or not len(o) or o.dtype.kind not in 'iuf' or not np.isfinite(o).all() or np.max(np.abs(o))>10:
        raise ValueError('Finite bounded 137D observation required')
    s=field_slices()
    for name in ('policy_phase','physical_phase','recovery_phase','decision'):
        a=o[:,s[name]]
        if not np.isin(a,(0.,1.)).all() or not np.all(a.sum(axis=1)==1):raise ValueError('Invalid one-hot '+name)
    for name in s:
        if name.endswith('_valid') or name in ('pending','action_active','simulation_valid','invalid_latched','latched_guards','reference_release_pending'):
            if not np.isin(o[:,s[name]],(0.,1.)).all():raise ValueError('Invalid boolean '+name)
    pending=o[:,s['pending']][:,0].astype(bool)
    if np.any(pending!=(o[:,s['decision']][:,0]==0)):raise ValueError('Decision/pending mismatch')
    phase=np.argmax(o[:,s['policy_phase']],axis=1)
    allowed=(phase==2)|((mode=='F50')&(phase==0))
    expected=allowed & (o[:,s['physical_phase']][:,0]==1) & ~pending & (o[:,s['simulation_valid']][:,0]==1)
    expected &= ~o[:,s['latched_guards']].any(axis=1) & ~o[:,s['invalid_latched']].any(axis=1)
    if np.any(o[:,s['action_active']][:,0]!=expected):raise ValueError('Same-cycle permission mismatch')
    return expected

def permission(observation,mode):
    o=np.asarray(observation)
    if o.shape!=(WIDTH,):raise ValueError('137D single observation required')
    return bool(permissions(o.reshape(1,WIDTH),mode)[0])

def attempt_specs(common):
    points=common['cases'];out=[]
    for stage in ('warmup','online','final'):
        for i,case in enumerate(points[:4] if stage!='final' else points):
            for mode in ('F50','S50'):
                out.append(dict(id=stage+'_'+mode+'_'+case['id'],stage=stage,mode=mode,case_index=i,case=case))
    for mode in ('F50','S50'):
        out.append(dict(id='restore_'+mode+'_'+points[0]['id'],stage='restore',mode=mode,case_index=0,case=points[0]))
    if len(out)!=28:raise ValueError('Exact registered matrix required')
    return out
