"""Differentiable v3 permission primitives, not a trainer or replay collector.

Evaluate the next critic on canonical_actions(next_action, next_active) BEFORE
critic_target. Callers own critic parameter freezing during actor evaluation.
Never call optimizer.step directly on an inactive loss: Adam momentum moves
parameters even with zero gradients. No candidate experience is authorized here.
"""
import math
import torch


def _numeric(value):
    if not isinstance(value, torch.Tensor) or not value.is_floating_point() or not torch.isfinite(value).all():
        raise ValueError('Finite floating-point tensor required')
    return value


def _column(value, n, device, *, boolean=False):
    if not isinstance(value, torch.Tensor) or value.shape != (n, 1) or value.device != device:
        raise ValueError('Same-device batch-by-one column required')
    if boolean:
        if value.dtype != torch.bool:
            raise ValueError('Boolean permission/termination column required')
    else:
        _numeric(value)
    return value


def _batch(value):
    _numeric(value)
    if value.ndim != 2 or value.shape[1] != 1 or not len(value):
        raise ValueError('Nonempty batch-by-one column required')
    return len(value), value.device


def _scalar(value, device):
    _numeric(value)
    if value.ndim != 0 or value.device != device:
        raise ValueError('Same-device scalar tensor required')
    return value


def canonical_actions(actions, active):
    _numeric(actions)
    if actions.ndim != 2 or actions.shape[1] != 4 or not len(actions) or (actions.abs() > 1).any():
        raise ValueError('Nonempty normalized batch-by-four actions required')
    _column(active, len(actions), actions.device, boolean=True)
    return torch.where(active, actions, torch.zeros_like(actions))


def critic_target(*, reward, discount, terminated, q_next, log_probability, alpha, next_active):
    n, device = _batch(reward)
    for value in (discount, q_next, log_probability):
        _column(value, n, device)
    _column(terminated, n, device, boolean=True)
    _column(next_active, n, device, boolean=True)
    _scalar(alpha, device)
    if alpha < 0 or ((discount < 0) | (discount > 1)).any():
        raise ValueError('Nonnegative alpha and discount in [0,1] required')
    with torch.no_grad():
        entropy = torch.where(next_active, log_probability, torch.zeros_like(log_probability))
        result = reward + torch.where(terminated, 0., discount*(q_next-alpha*entropy))
    return _numeric(result)


def actor_temperature_losses(*, q, log_probability, log_alpha, target_entropy, active):
    n, device = _batch(q)
    _column(log_probability, n, device)
    _column(active, n, device, boolean=True)
    _scalar(log_alpha, device)
    if not isinstance(target_entropy, (int, float)) or not math.isfinite(target_entropy):
        raise ValueError('Finite target entropy required')
    if not active.any():
        return None, None
    # Index active rows before averaging; inactive samples must not dilute loss.
    actor = (log_alpha.detach().exp()*log_probability[active]-q[active]).mean()
    temperature = -(log_alpha*(log_probability[active].detach()+target_entropy)).mean()
    return _numeric(actor), _numeric(temperature)


def masked_optimizer_step(loss, optimizer):
    """One optimizer only; not an atomic multi-network/SAC update transaction.

    None clears stale gradients but leaves parameters, moments and step counters
    untouched. Invalid loss/gradient raises before optimizer state is modified.
    """
    optimizer.zero_grad(set_to_none=True)
    if loss is None:
        return False
    _numeric(loss)
    if loss.ndim != 0 or not loss.requires_grad:
        raise ValueError('Differentiable scalar loss required')
    loss.backward()
    parameters = [p for group in optimizer.param_groups for p in group['params']]
    if not any(p.grad is not None for p in parameters):
        raise ValueError('Loss is disconnected from optimizer parameters')
    if any(p.grad is not None and not torch.isfinite(p.grad).all() for p in parameters):
        optimizer.zero_grad(set_to_none=True)
        raise ValueError('Nonfinite gradient; optimizer step refused')
    optimizer.step()
    return True
