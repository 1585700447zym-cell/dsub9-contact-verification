"""Real tensor boundaries: no simulation experiences and no SAC updates."""
import copy
import importlib

import pytest
import torch


def adapter():
    # A missing adapter is an assertion failure, not a collection/import error.
    assert importlib.util.find_spec('tools.learning.tensor_masks') is not None
    return importlib.import_module('tools.learning.tensor_masks')


def col(values, **kwargs):
    return torch.tensor(values, dtype=torch.float64, **kwargs).reshape(-1, 1)


def test_tensor_target_canonicalizes_inactive_actions_and_removes_entropy():
    m = adapter()
    active = torch.tensor([[False], [True]])
    actions = torch.ones((2, 4), dtype=torch.float64, requires_grad=True)
    canonical = m.canonical_actions(actions, active)
    torch.testing.assert_close(canonical, torch.tensor([[0.]*4, [1.]*4], dtype=torch.float64))
    target = m.critic_target(reward=col([0., 0.]), discount=col([.5, .5]),
        terminated=torch.zeros((2, 1), dtype=torch.bool), q_next=2+canonical.sum(1, keepdim=True),
        log_probability=col([-10., -10.], requires_grad=True), alpha=torch.tensor(.2), next_active=active)
    torch.testing.assert_close(target, col([1., 4.]))
    assert not target.requires_grad


def test_terminal_no_bootstrap_but_external_cut_retains_it():
    m = adapter()
    result = m.critic_target(reward=col([-2., -.1]), discount=col([.5, .25]),
        terminated=torch.tensor([[True], [False]]), q_next=col([4., 4.]),
        log_probability=col([0., 0.]), alpha=torch.tensor(.2),
        next_active=torch.ones((2, 1), dtype=torch.bool))
    torch.testing.assert_close(result, col([-2., .9]))


def test_canonical_action_gradient_preserves_active_and_blocks_inactive():
    actions = torch.ones((2, 4), dtype=torch.float64, requires_grad=True)
    result = adapter().canonical_actions(actions, torch.tensor([[True], [False]]))
    assert result.requires_grad
    result.sum().backward()
    torch.testing.assert_close(actions.grad, torch.tensor([[1.]*4, [0.]*4], dtype=torch.float64))


def test_actor_gradient_excludes_inactive_rows_and_temperature():
    m = adapter()
    q = torch.tensor([[3.], [999.]], dtype=torch.float64, requires_grad=True)
    p = torch.tensor([[-2.], [-100.]], dtype=torch.float64, requires_grad=True)
    alpha = torch.tensor(0., dtype=torch.float64, requires_grad=True)
    actor, _ = m.actor_temperature_losses(q=q, log_probability=p, log_alpha=alpha,
        target_entropy=-4., active=torch.tensor([[True], [False]]))
    assert actor.item() == pytest.approx(-5.)
    actor.backward()
    torch.testing.assert_close(q.grad, col([-1., 0.]))
    torch.testing.assert_close(p.grad, col([1., 0.]))
    assert alpha.grad is None


def test_temperature_gradient_does_not_flow_into_actor_or_critic():
    m = adapter()
    q = col([3., 999.], requires_grad=True)
    p = torch.tensor([[-2.], [-100.]], dtype=torch.float64, requires_grad=True)
    alpha = torch.tensor(1., dtype=torch.float64, requires_grad=True)
    _, temperature = m.actor_temperature_losses(q=q, log_probability=p, log_alpha=alpha,
        target_entropy=-4., active=torch.tensor([[True], [False]]))
    assert temperature.item() == pytest.approx(6.)
    temperature.backward()
    assert alpha.grad.item() == pytest.approx(6.)
    assert p.grad is None


def test_all_inactive_does_not_move_adam_parameters_or_momentum():
    m = adapter()
    parameter = torch.nn.Parameter(torch.tensor(1., dtype=torch.float64))
    optimizer = torch.optim.Adam([parameter], lr=.01)
    assert m.masked_optimizer_step(parameter.square(), optimizer) is True
    value = parameter.detach().clone()
    state = copy.deepcopy(optimizer.state_dict())
    losses = m.actor_temperature_losses(q=col([3.]), log_probability=col([-2.]),
        log_alpha=parameter, target_entropy=-4., active=torch.tensor([[False]]))
    assert losses == (None, None)
    for loss in losses:
        assert m.masked_optimizer_step(loss, optimizer) is False
    torch.testing.assert_close(parameter, value, rtol=0, atol=0)
    for key, tensor in state['state'][0].items():
        torch.testing.assert_close(optimizer.state_dict()['state'][0][key], tensor, rtol=0, atol=0)
    assert parameter.grad is None


@pytest.mark.parametrize('active', [torch.tensor([True, False]), torch.ones((2, 1)), torch.ones((1, 1), dtype=torch.bool)])
def test_mask_shape_and_boolean_type_cannot_broadcast(active):
    with pytest.raises(ValueError):
        adapter().canonical_actions(torch.ones((2, 4)), active)


@pytest.mark.parametrize('actions', [torch.ones((2, 6)), torch.full((2, 4), 1.1),
    torch.full((2, 4), float('nan')), torch.ones((2, 4), dtype=torch.int64), torch.empty((0, 4))])
def test_rejects_invalid_actions_even_when_inactive(actions):
    with pytest.raises(ValueError):
        adapter().canonical_actions(actions, torch.zeros((len(actions), 1), dtype=torch.bool))


@pytest.mark.parametrize('discount', [-.01, 1.01, float('nan')])
def test_rejects_invalid_discount(discount):
    with pytest.raises(ValueError):
        adapter().critic_target(reward=col([0.]), discount=col([discount]),
            terminated=torch.tensor([[False]]), q_next=col([1.]), log_probability=col([0.]),
            alpha=torch.tensor(.2), next_active=torch.tensor([[False]]))


def test_nonfinite_inactive_row_is_rejected_not_silently_hidden():
    with pytest.raises(ValueError):
        adapter().actor_temperature_losses(q=col([1., float('nan')]), log_probability=col([-1., -1.]),
            log_alpha=torch.tensor(0.), target_entropy=-4., active=torch.tensor([[True], [False]]))


def test_nonfinite_gradient_cannot_mutate_optimizer_state():
    m = adapter()
    p = torch.nn.Parameter(torch.tensor(0.))
    optimizer = torch.optim.Adam([p], lr=.01)
    with pytest.raises(ValueError):
        m.masked_optimizer_step(p.sqrt(), optimizer)  # finite loss, infinite derivative
    assert p.item() == 0. and not optimizer.state
