"""Disposable diagnostic only. --prepare/--verify never optimize; --run is once only."""
import argparse
from copy import deepcopy
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import time
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
SRC=ROOT/'deliverables/learning_chain/b2_contact_short_train_20260927'
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'tmp/learning_mpl_cache'))
sys.path.insert(0,str(ROOT))

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def dump(path,data): path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def suffix_labels(rewards,discounts,active,terminated):
    r=np.asarray(rewards,dtype=float); d=np.asarray(discounts,dtype=float)
    a=np.asarray(active,dtype=bool); t=np.asarray(terminated,dtype=bool)
    if (r.ndim!=1 or not len(r) or any(v.shape!=r.shape for v in (d,a,t)) or
        not np.isfinite(r).all() or not np.isfinite(d).all() or np.any((d<=0)|(d>1)) or
        not t[-1] or t[:-1].any() or not a.any() or a[-1]):
        raise ValueError('Complete finite terminated trajectory with active action then inactive suffix required')
    last=int(np.flatnonzero(a)[-1]); mask=np.arange(len(r))>=last
    returns=np.zeros(len(r),dtype=float)
    for i in range(len(r)-1,last-1,-1):
        returns[i]=r[i]+(d[i]*returns[i+1] if i+1<len(r) else 0.)
    return mask,returns,last

def select_targets(original,mask,exact,arm):
    import torch
    if arm=='one_step': return original
    if arm=='exact_inactive_suffix': return torch.where(mask,exact,original)
    raise ValueError('Unknown arm')

def load_inputs():
    import torch
    torch.set_num_threads(1)
    protocol=json.loads((HERE/'protocol_v2.json').read_text(encoding='utf-8'))
    assert protocol['critic_updates_per_arm']==1000 and protocol['total_critic_updates']==2000
    assert protocol['arms']==['one_step','exact_inactive_suffix']
    assert digest(SRC/'manifest.json')=='e643d9b88c8a37cedcb0137575581ecc6133346f1062c77482f5db59237d159e'
    sealed=json.loads((SRC/'manifest.json').read_text(encoding='utf-8'))['files']
    for path,expected in sealed.items(): assert digest(ROOT/path)==expected,path
    cp=SRC/'run/training/checkpoints/contact_000003'
    assert digest(cp/'manifest.json')==protocol['checkpoint_manifest_sha256']
    data=(cp/'state.pt').read_bytes()
    assert hashlib.sha256(data).hexdigest()==json.loads((cp/'manifest.json').read_text())['state_sha256']
    state=torch.load(io.BytesIO(data),weights_only=True,map_location='cpu')
    sources=state['binding']['record']['source_sha256']
    for path,expected in sources.items(): assert digest(ROOT/path)==expected,path
    sets={}; arrays=[]; masks=[]; labels=[]
    for split,paths in [('train',sorted((SRC/'run/episodes').glob('*/episode.json.gz'))),
                        ('development',sorted((SRC/'evaluation_run/evaluation/episodes').glob('*/episode.json.gz')))]:
        sets[split]=[]
        for index,path in enumerate(paths):
            raw=json.loads(gzip.decompress(path.read_bytes())); rows=raw['transitions']
            assert raw['outcome']['simulation_valid'] and raw['outcome']['physical_stopped']
            assert raw['outcome']['task_outcome'] in ('FULL_SUCCESS','TASK_FAILURE')
            mask,returns,last=suffix_labels([r['reward'] for r in rows],[r['discount'] for r in rows],
                [r['action_active'] for r in rows],[r['terminated'] for r in rows])
            assert len(rows)-last-1==1000 and all(not r['truncated'] for r in rows)
            assert all(not r['next_action_active'] for r in rows[last:])
            assert all(r['action']==[0.]*4 for r in rows[last+1:])
            obs=torch.tensor([r['observation'] for r in rows],dtype=torch.float32)
            act=torch.tensor([r['action'] for r in rows],dtype=torch.float32)
            sets[split].append(dict(id=raw['episode_id'],outcome=raw['outcome']['task_outcome'],
                observations=obs,actions=act,returns=torch.tensor(returns,dtype=torch.float32),last=last))
            if split=='train':
                key,arr=state['replay']['episodes'][index]
                assert key==raw['episode_id'] and torch.equal(arr['observations'],obs) and torch.equal(arr['actions'],act)
                assert torch.equal(arr['rewards'],torch.tensor([r['reward'] for r in rows],dtype=torch.float32).reshape(-1,1))
                arrays.append(arr); masks.append(torch.tensor(mask).reshape(-1,1))
                labels.append(torch.tensor(returns,dtype=torch.float32).reshape(-1,1))
        assert len(sets[split])==4
    flat={k:torch.cat([a[k] for a in arrays]) for k in arrays[0]}
    flat['suffix']=torch.cat(masks); flat['exact']=torch.cat(labels)
    assert len(flat['observations'])==22722 and int(flat['suffix'].sum())==4004
    bindings={**sealed,**sources}
    for p in (HERE/'protocol_v2.json',HERE/'probe_v2.py',HERE/'test_probe_v2.py',HERE/'test_isolation_v2.py'):
        bindings[p.relative_to(ROOT).as_posix()]=digest(p)
    return protocol,state,flat,sets,bindings

def make_policy(state):
    import torch
    from gymnasium import spaces
    from stable_baselines3.sac.policies import SACPolicy
    p=SACPolicy(spaces.Box(-10.,10.,shape=(120,),dtype=np.float32),
        spaces.Box(-1.,1.,shape=(4,),dtype=np.float32),lambda _:.0003,
        net_arch=[256,256],activation_fn=torch.nn.ReLU)
    p.load_state_dict(state['updater']['policy'])
    p.actor.optimizer.load_state_dict(deepcopy(state['updater']['actor']))
    p.critic.optimizer.load_state_dict(deepcopy(state['updater']['critic']))
    p.set_training_mode(False)
    for v in p.actor.parameters(): v.requires_grad_(False)
    return p

def metrics(policy,sets):
    import torch
    result={}
    with torch.no_grad():
        for split,episodes in sets.items():
            rows=[]; errors={k:[] for k in ('terminal','suffix_start','last_active','suffix_all')}
            for ep in episodes:
                last=ep['last']; indices=[len(ep['observations'])-1,last+1,last]
                q=torch.cat(policy.critic(ep['observations'][last:],ep['actions'][last:]),1)
                minimum=q.min(1).values; g=ep['returns'][last:]
                entry=dict(id=ep['id'],outcome=ep['outcome'])
                for name,index in zip(('terminal','suffix_start','last_active'),indices):
                    j=index-last; error=abs(float(minimum[j]-g[j]))
                    errors[name].append(error)
                    entry[name]=dict(q_each=q[j].tolist(),q_min=float(minimum[j]),
                        realized_return=float(g[j]),absolute_error=error)
                errors['suffix_all'].extend((minimum[1:]-g[1:]).abs().tolist())
                rows.append(entry)
            summary={k:dict(mae=float(np.mean(v)),maximum=float(np.max(v)),n=len(v)) for k,v in errors.items()}
            result[split]=dict(episodes=rows,summary=summary)
    return result

def fixed_unchanged(policy,state):
    from tools.learning.sac_checkpoint import _same
    import torch
    expected={k[len('actor.'):]:v for k,v in state['updater']['policy'].items() if k.startswith('actor.')}
    assert _same(policy.actor.state_dict(),expected)
    assert _same(policy.actor.optimizer.state_dict(),state['updater']['actor'])
    assert all(v.grad is None for v in policy.actor.parameters())
    assert all(torch.isfinite(v).all() for v in policy.state_dict().values())

def run(protocol,state,flat,sets,bindings):
    import torch
    from tools.learning.tensor_masks import canonical_actions,critic_target
    run_dir=HERE/'run_v2'; run_dir.mkdir(exist_ok=False)
    dump(run_dir/'started.json',dict(protocol_sha256=digest(HERE/'protocol_v2.json'),bindings=bindings,
        diagnostic_only=True,maximum_critic_updates=2000))
    policies={name:make_policy(state) for name in protocol['arms']}
    # Loading CPU optimizer state can retain tensor storage. Prove that neither
    # arm can change its peer or the immutable source before consuming updates.
    for category in ('actor','critic'):
        members=[list(getattr(p,category).optimizer.state.values()) for p in policies.values()]
        source=list(state['updater'][category]['state'].values())
        for a,b,s in zip(*members,source):
            for k in ('step','exp_avg','exp_avg_sq'):
                assert len({a[k].data_ptr(),b[k].data_ptr(),s[k].data_ptr()})==3
                assert torch.equal(a[k],b[k]) and torch.equal(a[k],s[k])
    curves={name:{'0':metrics(p,sets)} for name,p in policies.items()}
    assert curves['one_step']['0']==curves['exact_inactive_suffix']['0']
    rng=np.random.Generator(np.random.PCG64()); rng.bit_generator.state=deepcopy(state['rng']['replay'])
    torch.set_rng_state(state['updater']['rng'].clone())
    alpha=state['updater']['alpha'].exp().clone()
    counts={name:0 for name in policies}; history=[]; hash_indices=hashlib.sha256()
    started=time.perf_counter()
    try:
        for step in range(1,1001):
            ix=rng.integers(0,22722,size=256); hash_indices.update(ix.tobytes())
            batch={k:v[ix] for k,v in flat.items()}
            with torch.no_grad():
                action,logp=policies['one_step'].actor.action_log_prob(batch['next_observations'])
                action=canonical_actions(action,batch['next_action_active'])
            row=dict(step=step,suffix_rows=int(batch['suffix'].sum()),terminal_rows=int(batch['terminated'].sum()))
            for name,p in policies.items():
                with torch.no_grad():
                    qnext=torch.cat(p.critic_target(batch['next_observations'],action),1).min(1,keepdim=True).values
                    original=critic_target(reward=batch['rewards'],discount=batch['discounts'],
                        terminated=batch['terminated'],q_next=qnext,log_probability=logp.reshape(-1,1),
                        alpha=alpha,next_active=batch['next_action_active'])
                    target=select_targets(original,batch['suffix'],batch['exact'],name)
                current=p.critic(batch['observations'],canonical_actions(batch['actions'],batch['action_active']))
                loss=.5*sum(torch.nn.functional.mse_loss(q,target) for q in current)
                assert torch.isfinite(loss)
                p.critic.optimizer.zero_grad(set_to_none=True); loss.backward()
                assert all(v.grad is None or torch.isfinite(v.grad).all() for v in p.critic.parameters())
                p.critic.optimizer.step(); counts[name]+=1
                with torch.no_grad():
                    for src,dst in zip(p.critic.parameters(),p.critic_target.parameters()):
                        dst.mul_(.995).add_(src,alpha=.005)
                row[name]=float(loss.detach())
            history.append(row)
            if step in protocol['measurement_steps']:
                for name,p in policies.items():
                    fixed_unchanged(p,state); curves[name][str(step)]=metrics(p,sets)
                print('Completed critic steps per arm:',step,flush=True)
        for name,p in policies.items():
            fixed_unchanged(p,state)
            assert all(int(v['step'])==5430 for v in p.critic.optimizer.state.values())
            torch.save(dict(diagnostic_only=True,critic=p.critic.state_dict(),target=p.critic_target.state_dict(),
                critic_optimizer=p.critic.optimizer.state_dict(),critic_updates=counts[name]),run_dir/f'{name}.pt')
        assert all(int(v['step'])==4430 for v in state['updater']['critic']['state'].values())
        for path,expected in bindings.items(): assert digest(ROOT/path)==expected,path
        result=dict(protocol=protocol,counts=counts,physical_episodes=0,actor_updates=0,temperature_updates=0,
            frozen_state_unchanged=True,source_unchanged=True,wall_s=time.perf_counter()-started,
            batch_indices_sha256=hash_indices.hexdigest(),curves=curves,history=history,
            final_models_sha256={name:digest(run_dir/f'{name}.pt') for name in policies})
        dump(run_dir/'results.json',result)
        print('Completed bounded diagnostic; total critic updates:',sum(counts.values()),flush=True)
    except BaseException as exc:
        dump(run_dir/'failure.json',dict(error=repr(exc),counts=counts,history=history,curves=curves,
            optimizer_steps={name:[int(v['step']) for v in p.critic.optimizer.state.values()] for name,p in policies.items()}))
        raise

def verify(state,sets,bindings):
    import torch
    run_dir=HERE/'run_v2'; result=json.loads((run_dir/'results.json').read_text(encoding='utf-8'))
    start=json.loads((run_dir/'started.json').read_text(encoding='utf-8'))
    assert bindings==start['bindings']
    assert result['counts']==dict(one_step=1000,exact_inactive_suffix=1000)
    assert len(result['history'])==1000 and not (run_dir/'failure.json').exists()
    initial=make_policy(state); assert metrics(initial,sets)==result['curves']['one_step']['0']
    for name in ('one_step','exact_inactive_suffix'):
        path=run_dir/f'{name}.pt'; assert digest(path)==result['final_models_sha256'][name]
        saved=torch.load(path,weights_only=True,map_location='cpu')
        assert saved['diagnostic_only'] and saved['critic_updates']==1000
        p=make_policy(state); p.critic.load_state_dict(saved['critic']); p.critic_target.load_state_dict(saved['target'])
        p.critic.optimizer.load_state_dict(saved['critic_optimizer']); fixed_unchanged(p,state)
        assert all(int(v['step'])==5430 for v in p.critic.optimizer.state.values())
        assert metrics(p,sets)==result['curves'][name]['1000']
    print('Independent verification passed: final metrics exact; counters, source hashes and frozen actor unchanged.')

if __name__=='__main__':
    parser=argparse.ArgumentParser(); group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare',action='store_true'); group.add_argument('--run',action='store_true')
    group.add_argument('--verify',action='store_true'); args=parser.parse_args()
    protocol,state,flat,sets,bindings=load_inputs()
    if args.prepare:
        preflight=dict(bindings=bindings,rows=22722,exact_suffix_rows=4004,
            initial_metrics=metrics(make_policy(state),sets),optimizer_updates=0,physical_episodes=0)
        dump(HERE/'preflight_v2.json',preflight); print('Preflight passed: 22722 rows, 4004 eligible suffix/last-action rows; 0 updates.')
    elif args.run:
        prepared=json.loads((HERE/'preflight_v2.json').read_text(encoding='utf-8'))
        assert prepared['bindings']==bindings
        run(protocol,state,flat,sets,bindings)
    else: verify(state,sets,bindings)
