"""Small watertight convex mesh primitives in millimetres."""

from __future__ import annotations

import numpy as np

from tools.mesh.stl_binary import StlMesh


def _face_normals(triangles: np.ndarray) -> np.ndarray:
    vertices = np.asarray(triangles, dtype=np.float64)
    normals = np.cross(vertices[:, 1] - vertices[:, 0], vertices[:, 2] - vertices[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    if np.any(lengths <= 1e-12):
        raise ValueError("generated mesh contains a degenerate triangle")
    return normals / lengths[:, np.newaxis]


def _signed_area(profile_xy: np.ndarray) -> float:
    following = np.roll(profile_xy, -1, axis=0)
    return float(0.5 * np.sum(profile_xy[:, 0] * following[:, 1] - following[:, 0] * profile_xy[:, 1]))


def _validate_convex(profile_xy: np.ndarray) -> None:
    edges = np.roll(profile_xy, -1, axis=0) - profile_xy
    following = np.roll(edges, -1, axis=0)
    turns = edges[:, 0] * following[:, 1] - edges[:, 1] * following[:, 0]
    significant = turns[np.abs(turns) > 1e-10]
    if significant.size and np.any(np.sign(significant) != np.sign(significant[0])):
        raise ValueError("profile must be convex")


def _cross_2d(first: np.ndarray, second: np.ndarray) -> float:
    return float(first[0] * second[1] - first[1] * second[0])


def _point_on_segment(point: np.ndarray, start: np.ndarray, end: np.ndarray) -> bool:
    if abs(_cross_2d(end - start, point - start)) > 1e-10:
        return False
    return bool(np.all(point >= np.minimum(start, end) - 1e-10) and np.all(point <= np.maximum(start, end) + 1e-10))


def _segments_intersect(a: np.ndarray, b: np.ndarray, c: np.ndarray, d: np.ndarray) -> bool:
    ab_c = _cross_2d(b - a, c - a)
    ab_d = _cross_2d(b - a, d - a)
    cd_a = _cross_2d(d - c, a - c)
    cd_b = _cross_2d(d - c, b - c)
    if ab_c * ab_d < -1e-20 and cd_a * cd_b < -1e-20:
        return True
    return any(
        (
            abs(ab_c) <= 1e-10 and _point_on_segment(c, a, b),
            abs(ab_d) <= 1e-10 and _point_on_segment(d, a, b),
            abs(cd_a) <= 1e-10 and _point_on_segment(a, c, d),
            abs(cd_b) <= 1e-10 and _point_on_segment(b, c, d),
        )
    )


def _validate_simple(profile_xy: np.ndarray) -> None:
    count = len(profile_xy)
    for first in range(count):
        first_end = (first + 1) % count
        for second in range(first + 1, count):
            second_end = (second + 1) % count
            if first == second or first_end == second or second_end == first:
                continue
            if _segments_intersect(
                profile_xy[first], profile_xy[first_end], profile_xy[second], profile_xy[second_end]
            ):
                raise ValueError("profile must not be self-intersecting")


def make_prism(profile_xy: np.ndarray, z0_mm: float, z1_mm: float) -> StlMesh:
    """Extrude one simple convex XY profile into a closed prism."""
    profile = np.asarray(profile_xy, dtype=np.float64)
    if profile.ndim != 2 or profile.shape[1:] != (2,) or len(profile) < 3:
        raise ValueError("profile_xy must have shape (point_count, 2) with at least three points")
    if not np.all(np.isfinite(profile)) or not np.isfinite([z0_mm, z1_mm]).all():
        raise ValueError("profile and depths must be finite")
    if not z0_mm < z1_mm:
        raise ValueError("expected z0_mm < z1_mm")
    edge_lengths = np.linalg.norm(np.roll(profile, -1, axis=0) - profile, axis=1)
    if np.any(edge_lengths <= 1e-10):
        raise ValueError("profile contains repeated adjacent points")
    _validate_simple(profile)
    area = _signed_area(profile)
    if abs(area) <= 1e-10:
        raise ValueError("profile area must be non-zero")
    if area < 0:
        profile = profile[::-1].copy()
    _validate_convex(profile)

    count = len(profile)
    bottom = np.column_stack((profile, np.full(count, z0_mm)))
    top = np.column_stack((profile, np.full(count, z1_mm)))
    triangles: list[np.ndarray] = []
    if count == 3:
        bottom_centre = bottom.mean(axis=0)
        top_centre = top.mean(axis=0)
        for index in range(count):
            following = (index + 1) % count
            triangles.append(np.array([bottom_centre, bottom[following], bottom[index]]))
            triangles.append(np.array([top_centre, top[index], top[following]]))
    else:
        for index in range(1, count - 1):
            triangles.append(np.array([bottom[0], bottom[index + 1], bottom[index]]))
            triangles.append(np.array([top[0], top[index], top[index + 1]]))
    for index in range(count):
        following = (index + 1) % count
        triangles.append(np.array([bottom[index], bottom[following], top[following]]))
        triangles.append(np.array([bottom[index], top[following], top[index]]))

    triangle_array = np.asarray(triangles, dtype=np.float32)
    return StlMesh(normals=_face_normals(triangle_array).astype(np.float32), triangles=triangle_array)


def make_annular_sector(
    inner_radius_mm: float,
    outer_radius_mm: float,
    angle0_rad: float,
    angle1_rad: float,
    z0_mm: float,
    z1_mm: float,
) -> StlMesh:
    """Create one independently closed convex four-corner annular wedge."""
    if not 0 < inner_radius_mm < outer_radius_mm:
        raise ValueError("expected 0 < inner radius < outer radius")
    if not angle0_rad < angle1_rad:
        raise ValueError("sector angle must increase")
    if angle1_rad - angle0_rad >= np.pi:
        raise ValueError("sector angle must be less than pi")
    profile = np.asarray(
        [
            [inner_radius_mm * np.cos(angle0_rad), inner_radius_mm * np.sin(angle0_rad)],
            [outer_radius_mm * np.cos(angle0_rad), outer_radius_mm * np.sin(angle0_rad)],
            [outer_radius_mm * np.cos(angle1_rad), outer_radius_mm * np.sin(angle1_rad)],
            [inner_radius_mm * np.cos(angle1_rad), inner_radius_mm * np.sin(angle1_rad)],
        ]
    )
    return make_prism(profile, z0_mm, z1_mm)
