"""Pure numerical bounds and wrench reference-point conversion."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray


def _finite_vector(value: ArrayLike, size: int, name: str) -> NDArray[np.float64]:
    try:
        vector = np.asarray(value, dtype=float)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite vector of shape ({size},)") from exc
    if vector.shape != (size,) or not np.all(np.isfinite(vector)):
        raise ValueError(f"{name} must be a finite vector of shape ({size},)")
    return vector


def limit_command(
    requested: ArrayLike,
    previous: ArrayLike,
    dt: float,
    velocity_limits: ArrayLike,
    acceleration_limits: ArrayLike,
) -> NDArray[np.float64]:
    """Bound a six-axis velocity command, then slew from a valid previous one.

    Linear components precede angular components. Limits are positive,
    component-wise magnitudes in units consistent with the commands and dt.
    No input is modified. A previous command outside the velocity bounds is
    rejected because both speed and slew bounds cannot generally be satisfied.
    """
    requested = _finite_vector(requested, 6, "requested")
    previous = _finite_vector(previous, 6, "previous")
    velocity_limits = _finite_vector(velocity_limits, 6, "velocity_limits")
    acceleration_limits = _finite_vector(acceleration_limits, 6, "acceleration_limits")
    try:
        period = np.asarray(dt, dtype=float)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("dt must be a positive finite scalar") from exc
    if period.shape != () or not np.isfinite(period) or period <= 0.0:
        raise ValueError("dt must be a positive finite scalar")
    if np.any(velocity_limits <= 0.0) or np.any(acceleration_limits <= 0.0):
        raise ValueError("velocity_limits and acceleration_limits must be strictly positive")
    if np.any(np.abs(previous) > velocity_limits):
        raise ValueError("previous command exceeds velocity_limits")

    bounded = np.clip(requested, -velocity_limits, velocity_limits)
    max_change = acceleration_limits * float(period)
    return np.clip(bounded, previous - max_change, previous + max_change)


def shift_wrench(
    wrench: ArrayLike, source_world: ArrayLike, target_world: ArrayLike
) -> NDArray[np.float64]:
    """Shift [force, torque] between points, keeping all axes in world frame.

    The new torque is source torque + (source - target) cross force.
    This changes the torque reference point only; no frame rotation is applied.
    """
    wrench = _finite_vector(wrench, 6, "wrench")
    source = _finite_vector(source_world, 3, "source_world")
    target = _finite_vector(target_world, 3, "target_world")
    return np.concatenate((wrench[:3], wrench[3:] + np.cross(source - target, wrench[:3])))
