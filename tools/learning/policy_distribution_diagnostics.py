"""Analytic diagnostics for locked non-gSDE squashed Gaussian SAC parameters.

Inputs come from separately authorized actor forwards. This module never
loads a model, consumes RNG or claims saturation probability is a safety risk.
"""
import math


def _vector(value, *, log_std=False):
    if (not isinstance(value, (list, tuple)) or len(value) != 4 or
            any(type(v) not in (int, float) or not math.isfinite(v) for v in value)):
        raise ValueError('Finite four-axis numeric distribution parameters required')
    if log_std and any(not -20. <= v <= 2. for v in value):
        raise ValueError('Parameters differ from locked SB3 log standard deviation bounds')
    return [float(v) for v in value]


def diagnose(reference_mean, reference_log_std, mean, log_std):
    """KL(candidate || reference), P(|tanh(U)| >= .95), and tanh(mu).

    tanh(mu) is the deterministic action, NOT E[tanh(U)]. Gaussian KL equals
    squashed KL under the same invertible tanh transform in exact arithmetic.
    These metrics apply only to the supplied observations, without guarantees
    about unobserved contact states, physical outcomes or temporal correlation.
    """
    reference_mean = _vector(reference_mean)
    reference_log_std = _vector(reference_log_std, log_std=True)
    mean = _vector(mean)
    log_std = _vector(log_std, log_std=True)
    threshold = math.atanh(.95)
    probabilities, divergences = [], []
    try:
        for ref_mu, ref_log, mu, log in zip(reference_mean, reference_log_std, mean, log_std):
            sd, ref_sd = math.exp(log), math.exp(ref_log)
            probability = .5*math.erfc((threshold-mu)/(sd*math.sqrt(2)))
            probability += .5*math.erfc((threshold+mu)/(sd*math.sqrt(2)))
            kl = ref_log-log + .5*((sd/ref_sd)**2 + ((mu-ref_mu)/ref_sd)**2) - .5
            if not math.isfinite(kl) or not math.isfinite(probability) or kl < -1e-12:
                raise ValueError('Nonfinite or invalid distribution diagnostic')
            probabilities.append(min(1., max(0., probability)))
            divergences.append(max(0., kl))
        total = sum(divergences)
        if not math.isfinite(total):
            raise ValueError('Nonfinite total KL')
    except OverflowError:
        raise ValueError('Distribution diagnostic overflow') from None
    return dict(deterministic_actions=[math.tanh(v) for v in mean],
        reference_deterministic_actions=[math.tanh(v) for v in reference_mean],
        saturation_probability_per_axis=probabilities, kl_to_reference_per_axis=divergences,
        kl_to_reference=total)


def select_state_indices(transitions, *, count=64):
    """Evenly select distinct active archive indices, preserving original order."""
    if type(count) is not int or count < 2 or not isinstance(transitions, list):
        raise ValueError('Positive sample count >=2 and archive list required')
    if any(not isinstance(r, dict) or type(r.get('action_active')) is not bool for r in transitions):
        raise ValueError('Boolean archived action permission required')
    active = [i for i, row in enumerate(transitions) if row['action_active']]
    if len(active) < count:
        raise ValueError('Insufficient active states; duplicate samples forbidden')
    return [active[j*(len(active)-1)//(count-1)] for j in range(count)]
