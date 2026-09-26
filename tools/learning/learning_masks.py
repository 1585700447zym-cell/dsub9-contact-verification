"""NumPy specification oracle, NOT a differentiable SAC trainer.

The future tensor adapter must detach alpha in actor loss and log_probability
in temperature loss; skip both optimizer steps when the returned losses are
None. These numeric checks do not certify framework gradients or optimizer state.
"""
import math
import numpy as np


def _column(value, size, *, boolean=False):
    a = np.asarray(value)
    if a.shape != (size, 1) or (boolean and a.dtype.kind != 'b'):
        raise ValueError('Expected batch-by-one column, boolean for masks')
    if not boolean and not np.isfinite(a).all():
        raise ValueError('Finite numeric column required')
    return a


def canonical_actions(actions, active):
    a = np.asarray(actions, dtype=float)
    if a.ndim != 2 or a.shape[1] != 4 or not np.isfinite(a).all() or np.any(abs(a) > 1):
        raise ValueError('Finite normalized batch-by-four actions required')
    mask = _column(active, len(a), boolean=True)
    return np.where(mask, a, 0.)


def critic_target(*, reward, discount, terminated, q_next, log_probability, alpha, next_active):
    n = len(reward)
    r, g, q, p = [_column(x, n) for x in (reward, discount, q_next, log_probability)]
    end, active = [_column(x, n, boolean=True) for x in (terminated, next_active)]
    if not math.isfinite(alpha) or alpha < 0 or np.any((g < 0) | (g > 1)):
        raise ValueError('Nonnegative finite alpha and discount in [0,1] required')
    return r + np.where(end, 0., g*(q-alpha*np.where(active, p, 0.)))


def actor_temperature_losses(*, q, log_probability, log_alpha, target_entropy, active):
    n = len(q)
    q, p = [_column(x, n) for x in (q, log_probability)]
    mask = _column(active, n, boolean=True)
    if not math.isfinite(log_alpha) or not math.isfinite(target_entropy):
        raise ValueError('Finite entropy settings required')
    if not mask.any():
        return None, None
    return (float(np.mean(math.exp(log_alpha)*p[mask]-q[mask])),
            float(np.mean(-log_alpha*(p[mask]+target_entropy))))
