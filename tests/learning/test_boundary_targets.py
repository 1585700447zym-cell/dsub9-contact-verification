"""No optimizer or physics calls: catch premature credit, leakage and quotas."""
from copy import deepcopy
import importlib
import math
import numpy as np
import pytest
import torch
from tools.learning.audited_replay import AuditedReplay


def api(): return importlib.import_module('tools.learning.boundary_targets')


def raw_episode(identity='a', active=(True, False, True, False, False), terminal_reward=10.):
    rows=[]
    for i, flag in enumerate(active):
        rows.append(dict(observation=[i/10]*120,next_observation=[(i+1)/10]*120,
            action=[.2]*4 if flag else [0.]*4,reward=terminal_reward if i==len(active)-1 else -1.,
            dt=.002,discount=math.exp(-.002/10),terminated=i==len(active)-1,truncated=False,
            action_active=flag,next_action_active=active[i+1] if i+1<len(active) else False))
    return dict(episode_id=identity,transitions=rows,fault=None,
        guard_facts=dict(simulation_valid=True,contact_reasons=[],motion_reasons=[],invalid_reasons=[]),
        outcome=dict(simulation_valid=True,physical_stopped=True,valid_for_learning=True,
                     guard_violations=dict(contact=False,motion=False),task_outcome='FULL_SUCCESS'))


def test_only_final_inactive_suffix_and_last_decision_get_original_discounted_return():
    raw=raw_episode(); before=deepcopy(raw)
    target,mask,boundary=api().exact_tail(raw)
    g=math.exp(-.002/10)
    assert boundary==2
    assert mask.tolist()==[False,False,True,True,True]
    assert target[2:]==pytest.approx([-1-g+10*g*g,-1+10*g,10.],abs=1e-12)
    assert raw==before


def test_late_guard_penalty_is_used_without_a_second_or_early_success_reward():
    raw=raw_episode(terminal_reward=-10.)
    raw['outcome']['task_outcome']='TASK_FAILURE'
    targets,_,_=api().exact_tail(raw)
    assert targets[-1]==-10 and targets[2]<-11.9


def test_external_truncation_keeps_bootstrap_and_gets_no_exact_terminal_label():
    raw=raw_episode(); raw['transitions'][-1].update(terminated=False,truncated=True)
    targets,mask,boundary=api().exact_tail(raw)
    assert boundary is None and not mask.any() and not targets.any()


@pytest.mark.parametrize('fault',('invalid','discontinuous','bad_discount','nonfinite'))
def test_invalid_or_discontinuous_episode_never_produces_labels(fault):
    raw=raw_episode()
    if fault=='invalid': raw['outcome']['valid_for_learning']=False
    elif fault=='discontinuous': raw['transitions'][2]['observation'][0]=2.
    elif fault=='bad_discount': raw['transitions'][2]['discount']=.99
    else: raw['transitions'][2]['reward']=float('nan')
    with pytest.raises(ValueError): api().exact_tail(raw)


def test_boundary_quota_changes_only_critic_batch_and_rng_restores_next_batch():
    replay=AuditedReplay(capacity=1000); index=api().BoundaryIndex()
    for identity in ('a','b','c','d'):
        raw=raw_episode(identity); replay.publish(identity,raw['transitions'],outcome=raw['outcome'],training_admitted=True)
        index.add(raw)
    rng=np.random.default_rng(10); brng=np.random.default_rng(20)
    state=(deepcopy(rng.bit_generator.state),deepcopy(brng.bit_generator.state))
    result=index.sample(replay,rng=rng,boundary_rng=brng)
    expected_rng=np.random.default_rng(); expected_rng.bit_generator.state=state[0]
    expected=replay.sample(256,rng=expected_rng)
    assert torch.equal(expected.observations,result.actor.observations)
    assert torch.equal(result.critic.observations[:240],result.actor.observations[:240])
    assert result.critic.action_active[-16:].all()
    assert result.mask[-16:].all()
    assert all(row==2 for _,row in result.indices[-16:])
    assert all(not t.requires_grad for t in (result.targets,result.mask))
    rng.bit_generator.state=state[0]; brng.bit_generator.state=state[1]
    again=index.sample(replay,rng=rng,boundary_rng=brng)
    assert again.indices==result.indices and torch.equal(again.targets,result.targets)


def test_no_boundary_refuses_update_instead_of_silently_changing_sampling():
    raw=raw_episode(active=(False,False)); replay=AuditedReplay(capacity=100)
    replay.publish('a',raw['transitions'],outcome=raw['outcome'],training_admitted=True)
    index=api().BoundaryIndex(); index.add(raw)
    with pytest.raises(ValueError,match='boundary'):
        index.sample(replay,rng=np.random.default_rng(1),boundary_rng=np.random.default_rng(2))
