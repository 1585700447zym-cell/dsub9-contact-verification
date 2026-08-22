"""Continuous analytic signed-distance reference for one D-sub9 socket hole."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np


@dataclass(frozen=True)
class HoleParams:
    """Hole dimensions in metres."""

    bore_radius: float
    entry_radius: float
    entry_depth: float
    bore_depth: float
    outer_radius: float

    def __post_init__(self) -> None:
        values = (
            self.bore_radius,
            self.entry_radius,
            self.entry_depth,
            self.bore_depth,
            self.outer_radius,
        )
        if not all(math.isfinite(value) for value in values):
            raise ValueError("hole parameters must be finite")
        if not 0.0 < self.bore_radius < self.entry_radius < self.outer_radius:
            raise ValueError("expected 0 < bore_radius < entry_radius < outer_radius")
        if not 0.0 < self.entry_depth < self.bore_depth:
            raise ValueError("expected 0 < entry_depth < bore_depth")


def _query_point(point_m: np.ndarray) -> np.ndarray:
    point = np.asarray(point_m, dtype=float)
    if point.shape != (3,) or not np.all(np.isfinite(point)):
        raise ValueError("point_m must contain three finite coordinates")
    return point


def _finite_annulus_distance_gradient(
    point: np.ndarray,
    inner_radius: float,
    outer_radius: float,
    z_min: float,
    z_max: float,
) -> tuple[float, np.ndarray]:
    """Exact SDF and gradient of a finite annulus, negative in material.

    Rotational symmetry reduces the solid to the rectangle
    ``[inner_radius, outer_radius] x [z_min, z_max]`` in the ``(r, z)``
    half-plane.  The standard exact rectangle SDF is then revolved about Z.
    At symmetry/tie points the returned gradient is a deterministic
    subgradient; callers test derivatives away from CSG ties.
    """

    x, y, z = point
    radius = math.hypot(x, y)
    radial_midpoint = 0.5 * (inner_radius + outer_radius)
    radial_half_width = 0.5 * (outer_radius - inner_radius)
    axial_midpoint = 0.5 * (z_min + z_max)
    axial_half_width = 0.5 * (z_max - z_min)

    radial_delta = radius - radial_midpoint
    axial_delta = z - axial_midpoint
    q_radial = abs(radial_delta) - radial_half_width
    q_axial = abs(axial_delta) - axial_half_width
    outside_radial = max(q_radial, 0.0)
    outside_axial = max(q_axial, 0.0)
    outside_distance = math.hypot(outside_radial, outside_axial)
    distance = outside_distance + min(max(q_radial, q_axial), 0.0)

    derivative_q_radial = 0.0
    derivative_q_axial = 0.0
    if outside_distance > 0.0:
        derivative_q_radial = outside_radial / outside_distance
        derivative_q_axial = outside_axial / outside_distance
    elif q_radial >= q_axial:
        derivative_q_radial = 1.0
    else:
        derivative_q_axial = 1.0

    radial_sign = 1.0 if radial_delta > 0.0 else -1.0 if radial_delta < 0.0 else 0.0
    axial_sign = 1.0 if axial_delta > 0.0 else -1.0 if axial_delta < 0.0 else 0.0
    derivative_radius = derivative_q_radial * radial_sign
    gradient = np.zeros(3, dtype=float)
    if radius > 0.0:
        gradient[0] = derivative_radius * x / radius
        gradient[1] = derivative_radius * y / radius
    gradient[2] = derivative_q_axial * axial_sign
    return distance, gradient


def hole_distance(point_m: np.ndarray, params: HoleParams) -> float:
    """Return positive distance in free space and negative in socket material."""

    point = _query_point(point_m)
    entry_distance, _ = _finite_annulus_distance_gradient(
        point, params.entry_radius, params.outer_radius, 0.0, params.entry_depth
    )
    main_distance, _ = _finite_annulus_distance_gradient(
        point,
        params.bore_radius,
        params.outer_radius,
        params.entry_depth,
        params.bore_depth,
    )
    return min(entry_distance, main_distance)


def hole_gradient(point_m: np.ndarray, params: HoleParams) -> np.ndarray:
    """Return the analytic gradient of :func:`hole_distance`."""

    point = _query_point(point_m)
    entry_distance, entry_gradient = _finite_annulus_distance_gradient(
        point, params.entry_radius, params.outer_radius, 0.0, params.entry_depth
    )
    main_distance, main_gradient = _finite_annulus_distance_gradient(
        point,
        params.bore_radius,
        params.outer_radius,
        params.entry_depth,
        params.bore_depth,
    )
    return entry_gradient if entry_distance <= main_distance else main_gradient
