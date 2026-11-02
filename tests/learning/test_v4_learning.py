"""Real 137D tensors/Adam, schema permissions and whole-episode quarantine."""
from copy import deepcopy
from dataclasses import replace
import importlib,math
import numpy as np
import pytest
import torch
from tools.learning.audited_replay import ReplayBatch
from tools.learning.sac_checkpoint import _same

def contract():return importlib.import_module('tools.learning.v4_pilot_contract')
def updater(mode='F50'):
    from tools.learning.v4_sac import V4Updater
    return V4Updater(contract().learning_config(mode))

def obs(mode='F50',active=True,value=.2):
    c=contract().learning_config(mode);s={f['name']:slice(f['start'],f['start']+f['width']) for f in c['schema']}
    o=np.zeros(137,dtype=np.float32)
    for name,i in [('policy_phase',2 if active else 0),('physical_phase',0),('recovery_phase',0),('decision',0)]:
        o[s[name].start+i]=1
    o[s['simulation_valid']]=1;o[s['action_active']]=float(active if mode=='S50' else True)
    if not active and mode=='F50':
        o[s['physical_phase']]=0;o[s['physical_phase'].start+1]=1
        o[s['decision']]=0;o[s['decision'].start+4]=1;o[s['pending']]=1;o[s['action_active']]=0
    o[120:137]=value
    for name in s:
        if name.endswith('_valid') or name=='reference_release_pending':
            if s[name].start>=120:o[s[name]]=0
    return o

def rows(mode='F50',active=True):
    x=obs(mode,active);y=obs(mode,False);dt=.002
    return [dict(observation=x.tolist(),next_observation=x.tolist(),action=[.1]*4 if active else [0]*4,
        reward=-.1,dt=dt,discount=math.exp(-dt/10),terminated=False,truncated=False,
        action_active=active,next_action_active=active),
        dict(observation=x.tolist(),next_observation=y.tolist(),action=[.1]*4 if active else [0]*4,
        reward=9.9,dt=dt,discount=math.exp(-dt/10),terminated=True,truncated=False,
        action_active=active,next_action_active=False)]

def batch(mode='F50',active=True):
    a=obs(mode,active);n=16
    return ReplayBatch(observations=torch.tensor(np.tile(a,(n,1))),next_observations=torch.tensor(np.tile(a,(n,1))),
        actions=torch.full((n,4),.1 if active else 0.),rewards=torch.full((n,1),-.1),discounts=torch.full((n,1),math.exp(-.002/10)),
        dt=torch.full((n,1),.002),terminated=torch.zeros(n,1,dtype=torch.bool),truncated=torch.zeros(n,1,dtype=torch.bool),
        action_active=torch.full((n,1),active),next_action_active=torch.full((n,1),active))

def test_shared_zero_origin_and_appended_fields_really_reach_actor():
    f=updater('F50');s=updater('S50');assert f.fingerprints()==s.fingerprints()
    a=obs();b=a.copy();b[120:123]+=.5
    assert not np.array_equal(f.predict(a,deterministic=True)[0],f.predict(b,deterministic=True)[0])
    assert f.policy.observation_space.shape==(137,)

def test_schema_permission_rejects_false_activity_and_old_width():
    m=contract();o=obs('S50',True);assert m.permission(o,'S50')
    o[m.field_slices()['action_active']]=0
    with pytest.raises(ValueError):m.permission(o,'S50')
    with pytest.raises(ValueError):m.permission(np.zeros(120),'F50')

def test_inactive_preserves_actor_temperature_adam_momentum():
    u=updater('S50');u.update(batch('S50',True));before=u._snapshot()
    stats=u.update(batch('S50',False));after=u._snapshot()
    assert _same(before['actor'],after['actor']) and _same(before['temperature'],after['temperature'])
    assert _same(before['alpha'],after['alpha'])
    for k,v in before['policy'].items():
        if k.startswith('actor.'):assert torch.equal(v,after['policy'][k])
    assert stats['actor_loss'] is None and u.counts==dict(critic=2,actor=1,temperature=1,target=2)

def test_bad_shape_or_permission_rolls_back_before_any_update():
    u=updater();before=u._snapshot();bad=replace(batch(),observations=torch.zeros(16,120))
    with pytest.raises(ValueError):u.update(bad)
    assert u.failed and _same(before,u._snapshot())

def test_next_inactive_zero_action_and_entropy_match_oracle(monkeypatch):
    u=updater('S50');b=batch('S50',False);b.terminated[0]=True;b.truncated[1]=True
    seen=[]
    def q(o,a):seen.append(a.clone());return torch.full((len(a),1),3.),torch.full((len(a),1),5.)
    monkeypatch.setattr(u.policy.critic_target,'forward',q)
    target=u.targets(b)
    assert not torch.count_nonzero(seen[0]) and target[0].item()==pytest.approx(-.1)
    torch.testing.assert_close(target[1:],b.rewards[1:]+3*b.discounts[1:],rtol=0,atol=1e-7)

def test_whole_replay_rejects_invalid_episode_and_old_or_wrong_flags():
    from tools.learning.v4_replay import V4Replay
    r=V4Replay(mode='F50',capacity=30);data=rows();out=dict(simulation_valid=True,physical_stopped=True,valid_for_learning=True)
    result=r.publish('invalid',data,outcome=dict(out,simulation_valid=False,valid_for_learning=False),training_admitted=True)
    assert result['committed']==0 and len(r)==0
    bad=deepcopy(data);bad[0]['observation']=[0]*120
    with pytest.raises(ValueError):r.publish('old',bad,outcome=out,training_admitted=True)
    bad=deepcopy(data);bad[0]['action_active']=False
    with pytest.raises(ValueError):r.publish('mismatch',bad,outcome=out,training_admitted=True)
    assert r.publish('good',data,outcome=out,training_admitted=True)['committed']==2
    sampled=r.sample(8,rng=np.random.default_rng(11));assert sampled.observations.shape==(8,137)
    with pytest.raises(RuntimeError):r.publish('good',data,outcome=out,training_admitted=True)

def test_boundary_targets_include_terminal_tail_without_rewriting_actor_batch():
    from tools.learning.v4_replay import V4BoundaryIndex,V4Replay
    raw=dict(episode_id='a',transitions=rows(),outcome=dict(simulation_valid=True,physical_stopped=True,valid_for_learning=True))
    index=V4BoundaryIndex('F50');index.add(raw);targets,mask,boundary=index.entries['a']
    assert boundary==1 and mask.tolist()==[False,True] and targets[1]==pytest.approx(9.9)
    replay=V4Replay(mode='F50',capacity=30);replay.publish('a',raw['transitions'],outcome=raw['outcome'],training_admitted=True)
    b=index.sample(replay,rng=np.random.default_rng(9),boundary_rng=np.random.default_rng(10))
    assert b.actor.observations.shape==(256,137) and len(b.indices)==256
    assert all(k=='a' and i==1 for k,i in b.indices[-16:]) and b.mask[-16:].all()

def test_deactivated_action_is_not_published_as_nonzero_experience():
    from tools.learning.v4_replay import V4Replay
    data=rows('S50',False);data[0]['action']=[.1]*4
    r=V4Replay(mode='S50',capacity=10)
    with pytest.raises(ValueError):r._prepare(data)

def test_mixed_batch_updates_actor_only_for_active_rows():
    u=updater('S50');b=batch('S50',True);inactive=obs('S50',False)
    b.observations[8:]=torch.tensor(inactive);b.next_observations[8:]=torch.tensor(inactive)
    b.action_active[8:]=False;b.next_action_active[8:]=False;b.actions[8:]=0
    stats=u.update(b)
    assert stats['active_rows']==8 and u.counts==dict(critic=1,actor=1,temperature=1,target=1)

def test_boolean_observations_cannot_be_coerced_into_training_vectors():
    from tools.learning.v4_replay import V4Replay
    data=rows();data[0]['observation']=np.asarray(data[0]['observation'],dtype=bool)
    with pytest.raises(ValueError):V4Replay(mode='F50',capacity=20)._prepare(data)
