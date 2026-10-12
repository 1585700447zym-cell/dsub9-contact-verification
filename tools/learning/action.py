"""Pure v3 action transforms; does not authorize a physical rollout."""
import numpy as np
from tools.dynamics.safety import limit_command

DEFAULT_ACTION_SCALE = (.00015, .00015, .005, .005)


def validated_action_scale(scale):
    value = np.asarray(scale, dtype=float)
    if (value.shape != (4,) or not np.isfinite(value).all() or
            np.any(value <= 0) or np.any(value > DEFAULT_ACTION_SCALE)):
        raise ValueError('Finite positive shape4 scale within qualified maximum required')
    return tuple(float(v) for v in value)


def normalized_action(action4):
    try:
        value = np.asarray(action4, dtype=float)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError('Action must be finite shape4 in [-1,1]') from exc
    if value.shape != (4,) or not np.isfinite(value).all() or np.any(np.abs(value) > 1):
        raise ValueError('Action must be finite shape4 in [-1,1]')
    return value.copy()


def map_residual(action4, *, enabled: bool, action_scale=DEFAULT_ACTION_SCALE):
    value = normalized_action(action4)
    scale = validated_action_scale(action_scale)
    result = np.zeros(6)
    if enabled:
        result[[0, 1, 3, 4]] = value * scale
    return result


def residual_permission(policy_phase, physical_phase, *, pending, guard_latched):
    return bool(policy_phase in ('INSERT', 'SEARCH') and physical_phase == 'RUNNING'
                and not pending and not guard_latched)


def _stage_limit(command, phase):
    result = np.asarray(command, dtype=float).copy()
    if result.shape != (6,) or not np.isfinite(result).all():
        raise ValueError('Finite shape6 base command required')
    if phase in ('INSERT', 'SEARCH'):
        xy = .0005 if phase == 'INSERT' else .0003
        result[:2] = np.clip(result[:2], -xy, xy)
        result[3:5] = np.clip(result[3:5], -.02, .02)
    return result


def compose_command(base_command, action4, *, phase, enabled, previous_limited, dt,
                    action_scale=DEFAULT_ACTION_SCALE):
    action = normalized_action(action4)
    residual = map_residual(action, enabled=enabled, action_scale=action_scale)
    baseline = _stage_limit(base_command, phase)
    total = _stage_limit(np.asarray(base_command) + residual, phase)
    # Counterfactual ONLY at the command limiter; not a causal physics estimate.
    velocity = [.001]*3 + [.03]*3
    acceleration = [.005]*3 + [.3]*3
    limited = limit_command(total, previous_limited, dt, velocity, acceleration)
    zero_limited = limit_command(baseline, previous_limited, dt, velocity, acceleration)
    return total, dict(raw_action=action.tolist(), requested_residual=map_residual(action, enabled=True, action_scale=action_scale).tolist(),
                       enabled=bool(enabled), applied_residual=residual.tolist(),
                       experience_action=(action if enabled else np.zeros(4)).tolist(),
                       stage_limited_total=total.tolist(), predicted_limited_command=limited.tolist(),
                       zero_residual_limited_command=zero_limited.tolist(),
                       effective_command_delta=(limited-zero_limited).tolist())
