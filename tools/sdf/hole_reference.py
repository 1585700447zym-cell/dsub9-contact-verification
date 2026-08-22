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


def _step_profile_vertices(params: HoleParams) -> tuple[tuple[float, float], ...]:
    """Return the counter-clockwise boundary of the material in the (r, z) plane."""

    return (
        (params.entry_radius, 0.0),
        (params.outer_radius, 0.0),
        (params.outer_radius, params.bore_depth),
        (params.bore_radius, params.bore_depth),
        (params.bore_radius, params.entry_depth),
        (params.entry_radius, params.entry_depth),
    )


def _inside_polygon(radius: float, z: float, vertices: tuple[tuple[float, float], ...]) -> bool:
    """Odd-even point-in-polygon test; boundary classification is immaterial at distance zero."""

    inside = False
    previous_radius, previous_z = vertices[-1]
    for current_radius, current_z in vertices:
        if (current_z > z) != (previous_z > z):
            crossing_radius = current_radius + (z - current_z) * (
                previous_radius - current_radius
            ) / (previous_z - current_z)
            if radius < crossing_radius:
                inside = not inside
        previous_radius, previous_z = current_radius, current_z
    return inside


def _step_profile_distance_gradient(
    point: np.ndarray, params: HoleParams
) -> tuple[float, np.ndarray]:
    """Exact signed distance to the revolved six-edge stepped profile."""

    x, y, z = point
    radius = math.hypot(x, y)
    vertices = _step_profile_vertices(params)
    best_squared_distance = math.inf
    best_delta_radius = 0.0
    best_delta_z = 0.0
    best_outward_radius = 0.0
    best_outward_z = 0.0

    for index, start in enumerate(vertices):
        end = vertices[(index + 1) % len(vertices)]
        edge_radius = end[0] - start[0]
        edge_z = end[1] - start[1]
        edge_squared_length = edge_radius * edge_radius + edge_z * edge_z
        projection = (
            (radius - start[0]) * edge_radius + (z - start[1]) * edge_z
        ) / edge_squared_length
        projection = min(max(projection, 0.0), 1.0)
        closest_radius = start[0] + projection * edge_radius
        closest_z = start[1] + projection * edge_z
        delta_radius = radius - closest_radius
        delta_z = z - closest_z
        squared_distance = delta_radius * delta_radius + delta_z * delta_z
        # Strict comparison makes the first edge win exact ties in both implementations.
        if squared_distance < best_squared_distance:
            edge_length = math.sqrt(edge_squared_length)
            best_squared_distance = squared_distance
            best_delta_radius = delta_radius
            best_delta_z = delta_z
            best_outward_radius = edge_z / edge_length
            best_outward_z = -edge_radius / edge_length

    unsigned_distance = math.sqrt(best_squared_distance)
    inside = _inside_polygon(radius, z, vertices)
    distance = -unsigned_distance if inside else unsigned_distance
    if unsigned_distance > 0.0:
        sign = -1.0 if inside else 1.0
        gradient_radius = sign * best_delta_radius / unsigned_distance
        gradient_z = sign * best_delta_z / unsigned_distance
    else:
        gradient_radius = best_outward_radius
        gradient_z = best_outward_z

    gradient = np.zeros(3, dtype=float)
    if radius > 0.0:
        gradient[0] = gradient_radius * x / radius
        gradient[1] = gradient_radius * y / radius
    gradient[2] = gradient_z
    return distance, gradient


def hole_distance(point_m: np.ndarray, params: HoleParams) -> float:
    """Return positive distance in free space and negative in socket material."""

    point = _query_point(point_m)
    distance, _ = _step_profile_distance_gradient(point, params)
    return distance


def hole_gradient(point_m: np.ndarray, params: HoleParams) -> np.ndarray:
    """Return the analytic gradient of :func:`hole_distance`."""

    point = _query_point(point_m)
    _, gradient = _step_profile_distance_gradient(point, params)
    return gradient
