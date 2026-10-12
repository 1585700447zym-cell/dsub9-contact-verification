"""Learning-rate configuration and restore checks; no network or runtime imports."""
import math


def _rate(value):
    if type(value) not in (int, float):
        raise ValueError('Finite positive numeric learning rate required')
    try:
        result = float(value)
    except OverflowError:
        raise ValueError('Finite positive numeric learning rate required') from None
    if not math.isfinite(result) or result <= 0:
        raise ValueError('Finite positive numeric learning rate required')
    return result


def optimizer_learning_rates(settings):
    base = _rate(settings['learning_rate'])
    actor = _rate(settings.get('actor_learning_rate', base))
    return dict(actor=actor, critic=base, temperature=base)


def validate_optimizer_learning_rates(saved, settings):
    """Reject cross-branch Adam rates before any policy/optimizer is restored.

    Full checkpoint shape, moments, counters and qualification checks remain
    owned by the checkpoint validators. This guard does not grant admission.
    """
    rates = optimizer_learning_rates(settings)
    for role, expected in rates.items():
        try:
            groups = saved[role]['param_groups']
        except (KeyError, TypeError):
            raise ValueError('Missing optimizer learning rate groups: ' + role) from None
        if not isinstance(groups, list) or not groups:
            raise ValueError('Missing optimizer learning rate groups: ' + role)
        for group in groups:
            if not isinstance(group, dict) or _rate(group.get('lr')) != expected:
                raise ValueError('Optimizer learning rate differs: ' + role)
