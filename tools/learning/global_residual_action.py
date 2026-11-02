"""Opt-in G0/G1 command profiles; preserve the frozen v1 limiting algorithm."""
import math
import numpy as np
from tools.dynamics.safety import limit_command
from .five_axis_contract import SCALE as LEGACY_SCALE

SCALES = {'G0': LEGACY_SCALE, 'G1': (.0005, .0005, .0005, .0005, .005)}


def profile_config(profile):
    if not isinstance(profile, str) or profile not in SCALES:
        raise ValueError('Registered G0/G1 profile required')
    return dict(version=f'global_residual_{profile}_30s_v1',
        observation_version='five_axis_short_history_N2_30s_v1',
        action_scale=list(SCALES[profile]), task_deadline_s=30., max_cycles=16000)



class ReferenceEnvelopeInfeasible(ValueError):
    pass


def normalized_action(action):
    try:
        value = np.asarray(action, dtype=float)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError('Finite normalized five-vector required') from exc
    if value.shape != (5,) or not np.isfinite(value).all() or (abs(value) > 1).any():
        raise ValueError('Finite normalized five-vector required')
    return value.copy()


def map_residual(action, *, profile, enabled):
    scale = profile_config(profile)['action_scale']
    value = normalized_action(action)
    if type(enabled) not in (bool, np.bool_):
        raise ValueError('Boolean permission required')
    result = np.zeros(6)
    if enabled:
        result[[0, 1, 3, 4, 5]] = value * scale
    return result


def _stage_limit(command, phase):
    value = np.asarray(command, dtype=float).copy()
    if value.shape != (6,) or not np.isfinite(value).all():
        raise ValueError('Finite six-axis baseline command required')
    if phase in ('INSERT', 'SEARCH'):
        value[:2] = np.clip(value[:2], -.0005 if phase == 'INSERT' else -.00045,
                           .0005 if phase == 'INSERT' else .00045)
        value[3:] = np.clip(value[3:], -.02, .02)
    return value


def compose_command(base, action, *, profile, phase, enabled, previous_limited, dt,
                    reference_xy=None, radius=.0004):
    action = normalized_action(action)
    if enabled and phase not in ('INSERT', 'SEARCH'):
        raise ValueError('Residual forbidden in this stage')
    residual = map_residual(action, profile=profile, enabled=enabled)
    zero = _stage_limit(base, phase)
    total = _stage_limit(np.asarray(base) + residual, phase)
    velocity = [.001] * 3 + [.03] * 3
    acceleration = [.005] * 3 + [.3] * 3
    low = limit_command(zero, previous_limited, dt, velocity, acceleration)
    high = limit_command(total, previous_limited, dt, velocity, acceleration)
    log = dict(raw_action=action.tolist(), requested_residual=map_residual(action, profile=profile, enabled=True).tolist(),
        enabled=bool(enabled), applied_residual=residual.tolist(),
        experience_action=(action if enabled else np.zeros(5)).tolist(), reference_checked=False,
        reference_filter_fraction=1., unfiltered_stage_limited_total=total.tolist())
    log['composition_inputs'] = dict(base_command=np.asarray(base).tolist(),
        previous_limited_command=np.asarray(previous_limited).tolist(), phase=phase, dt=dt)
    if phase == 'SEARCH' and enabled:
        ref = np.asarray(reference_xy, dtype=float)
        if (ref.shape != (2,) or not np.isfinite(ref).all() or type(radius) not in (int, float)
                or not math.isfinite(radius) or radius <= 0):
            raise ValueError('Finite search reference and positive radius required')
        def inside(command):
            return np.linalg.norm(ref + command[:2] * dt) <= radius + 1e-12
        if np.linalg.norm(ref) > radius + 1e-12 or not inside(low):
            raise ReferenceEnvelopeInfeasible('Zero residual cannot remain inside search disk')
        log.update(reference_checked=True, reference_xy_m=ref.tolist(), reference_radius_limit_m=radius)
        if not inside(high):
            left, right = 0., 1.
            if np.linalg.norm(ref + low[:2] * dt) > radius - 1e-12:
                right = 0.
            for _ in range(56):
                middle = (left + right) / 2
                if np.linalg.norm(ref + (low + middle * (high - low))[:2] * dt) <= radius - 1e-12:
                    left = middle
                else:
                    right = middle
            total = low + left * (high - low)
            high = limit_command(total, previous_limited, dt, velocity, acceleration)
            if not inside(high):
                left = 0.; total = low.copy(); high = limit_command(total, previous_limited, dt, velocity, acceleration)
            if not inside(high):
                raise ReferenceEnvelopeInfeasible('Final drive command outside search disk')
            log['reference_filter_fraction'] = left
        log['predicted_reference_xy_m'] = (ref + high[:2] * dt).tolist()
    log.update(stage_limited_total=total.tolist(), predicted_limited_command=high.tolist(),
        zero_residual_limited_command=low.tolist(), effective_command_delta=(high - low).tolist())
    log.update(profile=profile, contract_version=profile_config(profile)['version'],
        pre_stage_total=(np.asarray(base) + residual).tolist(),
        stage_clip_delta=(np.asarray(base) + residual - np.asarray(log['unfiltered_stage_limited_total'])).tolist(),
        drive_clip_delta=(np.asarray(log['unfiltered_stage_limited_total']) -
                          limit_command(log['unfiltered_stage_limited_total'], previous_limited, dt, velocity, acceleration)).tolist())
    return total, log
