"""Input/target behavior without executing any optimizer steps."""
from dataclasses import replace
import pytest
import torch
from tools.learning.sac_update import SACUpdater
from tools.learning.admission import short_training_config
from tests.learning.test_sac_update import batch


def test_exact_labels_replace_only_eligible_targets_without_changing_transition():
    updater=SACUpdater(short_training_config()); b=batch()
    mask=torch.zeros((16,1),dtype=torch.bool); mask[-2:]=True
    b.next_action_active[-2:]=False
    labels=torch.zeros((16,1)); labels[-2:,0]=torch.tensor([7.,-2.])
    before=b.rewards.clone(); params=updater.fingerprints()
    target=updater.targets(b,exact_targets=(labels,mask))
    assert torch.equal(target[-2:],labels[-2:])
    assert torch.equal(b.rewards,before) and updater.fingerprints()==params


def test_actor_uses_original_states_even_when_critic_uses_boundary_states(monkeypatch):
    import tools.learning.sac_update as module
    updater=SACUpdater(short_training_config()); actor=batch(); critic=batch()
    actor.observations.fill_(.25); critic.observations.fill_(.75)
    calls=[]; original=updater.policy.actor.action_log_prob
    def observed(obs,*args,**kwargs):
        calls.append(obs.detach().clone()); return original(obs,*args,**kwargs)
    monkeypatch.setattr(updater.policy.actor,'action_log_prob',observed)
    # Exercise the update routing, not Adam. The real 3-update probe tests Adam.
    monkeypatch.setattr(module,'masked_optimizer_step',lambda loss,opt: None)
    updater.update(actor,critic_batch=critic)
    assert torch.equal(calls[-1],actor.observations)
    assert torch.equal(calls[0],critic.next_observations)


@pytest.mark.parametrize('problem',('shape','nan','future_action','grad'))
def test_bad_exact_labels_are_rejected_before_optimization(problem):
    updater=SACUpdater(short_training_config()); b=batch(False)
    labels=torch.zeros((16,1)); mask=torch.ones((16,1),dtype=torch.bool)
    if problem=='shape': labels=torch.zeros(16)
    elif problem=='nan': labels[0]=float('nan')
    elif problem=='future_action': b.next_action_active[0]=True
    else: labels.requires_grad_(True)
    with pytest.raises(ValueError): updater.targets(b,exact_targets=(labels,mask))
    assert updater.counts==dict(critic=0,actor=0,temperature=0,target=0)
