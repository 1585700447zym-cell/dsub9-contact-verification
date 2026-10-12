"""One authorized read-only critic probe, <=25000 state/action pairs, no actor."""
import os, sys, json, gzip, hashlib, importlib.abc
from pathlib import Path
from datetime import datetime

class NoSimulator(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in ('mujoco','stable_baselines3'):
            raise RuntimeError('Simulator and policy classes prohibited in this probe')
sys.meta_path.insert(0,NoSimulator())
import torch
import torch.nn.functional as F
torch.set_num_threads(1)
torch.set_grad_enabled(False)
def deny(*a,**k): raise RuntimeError('Optimization prohibited')
torch.optim.Adam.step=deny
torch.optim.SGD.step=deny
D=Path(__file__).resolve().parent
ROOT=D.parents[2];OLD=D.parent/'b2_atomic_repaired_cycle_20260929';RUN=OLD/'run'
OUT=D/'critic_probe';OUT.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
seal=read(OLD/'sealed_files.json');inputs={}
def check(p):
    key=p.relative_to(ROOT).as_posix();actual=sha(p)
    assert actual==seal[key],key
    inputs[key]=actual
    return p
def fingerprint(obj):
    h=hashlib.sha256()
    def add(x):
        h.update(type(x).__name__.encode())
        if isinstance(x,torch.Tensor):
            h.update(str((x.dtype,tuple(x.shape))).encode());h.update(x.contiguous().numpy().tobytes())
        elif isinstance(x,dict):
            for k in sorted(x,key=str):add(k);add(x[k])
        elif isinstance(x,(list,tuple)):
            for v in x:add(v)
        elif isinstance(x,bytes):h.update(x)
        else:h.update(repr(x).encode())
    add(obj);return h.hexdigest()
assert sha(OLD/'candidate.json')=='ab2fefe0ae4eb6850d5aae768dff7a7c952302e3893f68721fb41a4adf3de379'
checkpoints=read(check(RUN/'training/checkpoints.json'))
chosen=[c for c in checkpoints if Path(c['path']).name in ('train_03','train_04','train_06','train_07')]
assert [c['updates'] for c in chosen]==[500,1000,2000,2500]
ledger=read(check(RUN/'ledger.json'))
points={};tails={}
for entry in ledger['attempts']:
    name=entry['id'];folder=RUN/('initial/episodes' if entry['stage']=='initial' else 'training_episodes')/name
    raw=json.loads(gzip.decompress(check(folder/'episode.json.gz').read_bytes()));rs=raw['transitions']
    boundary=max(i for i,r in enumerate(rs) if r['action_active'])
    value=0.
    for r in reversed(rs[boundary:]):value=r['reward']+r['discount']*value
    tails[name]=dict(index=boundary,label=value,outcome=entry['result']['task_outcome'])
    indices=[boundary]
    if name in ('train_00','train_04','train_06','train_08'):
        indices+=list(range(max(0,boundary-500),boundary+1))
    for i in set(indices):
        r=rs[i]
        if not r['action_active']:continue
        points[(name,i)]=dict(episode=name,index=i,boundary=i==boundary,observation=r['observation'],
            action=r['action'],time_to_stop_s=raw['stop_time']-r['trace_row']['time_s'],
            phase=r['trace_row']['policy_phase'])
points=list(points.values())
planned=len(points)*3*4+4 # one independent Sequential check per checkpoint, also charged
assert planned<=25000
claim=dict(authorized_by='用户：批准这一次限定离线核对',started_at=datetime.now().astimezone().isoformat(),
    max_pairs=25000,planned_pairs=planned,reserved_pairs=0,physics=0,actor_forwards=0,optimizer_updates=0)
claimpath=OUT/'claim.json'
with claimpath.open('x',encoding='utf-8') as f:json.dump(claim,f,ensure_ascii=False,indent=2)
variants=('recorded','zero','half')
obs=torch.tensor([p['observation'] for p in points],dtype=torch.float32)
act=torch.tensor([p['action'] for p in points],dtype=torch.float32)
assert torch.isfinite(obs).all() and torch.isfinite(act).all()
assert obs.shape==(len(points),120) and act.shape==(len(points),4)
actions=(act,torch.zeros_like(act),act*.5)
features=torch.cat([torch.cat((obs,a),dim=1) for a in actions])
results=[]
for cp in chosen:
    path=RUN/cp['path'];manifest=read(check(path/'manifest.json'))
    assert sha(path/'manifest.json')==cp['sha256'] and sha(check(path/'state.pt'))==manifest['state_sha256']
    state=torch.load(path/'state.pt',map_location='cpu',weights_only=True)
    before=fingerprint(state);rng=torch.get_rng_state().clone()
    weights=state['updater']['policy']
    assert state['updater']['counts']==dict(critic=cp['updates'],actor=cp['updates'],temperature=cp['updates'],target=cp['updates'])
    names={f'critic.qf{q}.{j}.{part}' for q in (0,1) for j in (0,2,4) for part in ('weight','bias')}
    assert {k for k in weights if k.startswith('critic.')}==names
    claim['reserved_pairs']+=len(features)+1
    assert claim['reserved_pairs']<=25000
    claimpath.write_text(json.dumps(claim,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    values=[]
    for q in (0,1):
        y=features
        for j,shape in ((0,(256,124)),(2,(256,256)),(4,(1,256))):
            w=weights[f'critic.qf{q}.{j}.weight'];b=weights[f'critic.qf{q}.{j}.bias']
            assert tuple(w.shape)==shape and tuple(b.shape)==(shape[0],)
            y=F.linear(y,w,b)
            if j!=4:y=F.relu(y)
        assert torch.isfinite(y).all();values.append(y)
    # Independent construction for one archived pair; meta initialization consumes no RNG.
    for q in (0,1):
        with torch.device('meta'):
            net=torch.nn.Sequential(torch.nn.Linear(124,256),torch.nn.ReLU(),torch.nn.Linear(256,256),torch.nn.ReLU(),torch.nn.Linear(256,1))
        net.load_state_dict({k.removeprefix(f'critic.qf{q}.'):v for k,v in weights.items() if k.startswith(f'critic.qf{q}.')},assign=True)
        assert torch.allclose(net(features[:1]),values[q][:1],atol=1e-5,rtol=1e-5)
    assert torch.equal(rng,torch.get_rng_state()) and before==fingerprint(state)
    seen=set(state['archives'])
    scores=[]
    for i,p in enumerate(points):
        row={k:v for k,v in p.items() if k not in ('observation','action')}
        row['in_checkpoint_replay']=p['episode'] in seen
        row['scores']={variant:{'q1':values[0][v*len(points)+i].item(),'q2':values[1][v*len(points)+i].item(),
            'min_q':min(values[0][v*len(points)+i].item(),values[1][v*len(points)+i].item())} for v,variant in enumerate(variants)}
        if row['boundary']:row['exact_tail_label']=tails[p['episode']]['label']
        scores.append(row)
    results.append(dict(checkpoint=cp,complete_state_unchanged=True,process_rng_unchanged=True,
        state_fingerprint=before,state_file_sha256=manifest['state_sha256'],scores=scores))
assert claim['reserved_pairs']==planned
assert 'mujoco' not in sys.modules and 'stable_baselines3' not in sys.modules
result=dict(status='completed',state_action_pairs=planned,states=len(points),physics=0,optimizer_updates=0,
    actor_forwards=0,checkpoints=results,inputs_sha256=inputs,
    score_scope='Twin online critics, not target networks; zero/half scores are model rankings, not causal physical outcomes.')
(OUT/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
summary=[]
for result in results:
    boundary=[r for r in result['scores'] if r['boundary']]
    summary.append(dict(updates=result['checkpoint']['updates'],boundary=boundary))
(OUT/'boundary_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'completed_pairs':planned,'states':len(points),'checkpoints':4,'physics':0,'updates':0,'actor':0}))
for s in summary:
    print(s['updates'],[(r['episode'],round(r['scores']['recorded']['min_q'],3),round(r['exact_tail_label'],3),r['in_checkpoint_replay']) for r in s['boundary']])
