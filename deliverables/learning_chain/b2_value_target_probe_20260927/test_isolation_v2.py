"""Cross-arm restore isolation regression. Zero optimizer updates."""
import importlib.util
from pathlib import Path
import torch

def load():
    here=Path(__file__).resolve().parent
    spec=importlib.util.spec_from_file_location('probe_v2',here/'probe_v2.py')
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    state=torch.load(m.SRC/'run/training/checkpoints/contact_000003/state.pt',weights_only=True,map_location='cpu')
    return m,state

def test_all_adam_tensors_are_independent_of_other_arm_and_source():
    m,s=load(); a=m.make_policy(s); b=m.make_policy(s)
    for category in ('actor','critic'):
        av=list(getattr(a,category).optimizer.state.values())
        bv=list(getattr(b,category).optimizer.state.values())
        source=list(s['updater'][category]['state'].values())
        for x,y,z in zip(av,bv,source):
            for key in ('step','exp_avg','exp_avg_sq'):
                assert torch.equal(x[key],y[key]) and torch.equal(x[key],z[key])
                assert len({x[key].data_ptr(),y[key].data_ptr(),z[key].data_ptr()})==3

def test_mutating_one_arm_moments_leaves_peer_and_source_unchanged():
    m,s=load(); a=m.make_policy(s); b=m.make_policy(s)
    x=next(iter(a.critic.optimizer.state.values()))
    y=next(iter(b.critic.optimizer.state.values()))
    z=next(iter(s['updater']['critic']['state'].values()))
    old={k:v.clone() for k,v in z.items()}
    # Deliberate in-memory sentinel, not an optimizer update; objects discarded.
    x['step'].add_(7); x['exp_avg'].add_(1); x['exp_avg_sq'].add_(2)
    for k in old:
        assert torch.equal(y[k],old[k]) and torch.equal(z[k],old[k])
