"""Plane-section extraction and CAD-derived centred D-loop selection."""

from __future__ import annotations

from collections import defaultdict
from itertools import product

import numpy as np

from tools.mesh.stl_binary import StlMesh


def polygon_area(profile_xy: np.ndarray) -> float:
    """Return the signed area of an unclosed XY polygon."""
    profile = np.asarray(profile_xy, dtype=np.float64)
    following = np.roll(profile, -1, axis=0)
    return float(0.5 * np.sum(profile[:, 0] * following[:, 1] - following[:, 0] * profile[:, 1]))


def polygon_centroid(profile_xy: np.ndarray) -> np.ndarray:
    """Return the area centroid of an unclosed XY polygon."""
    profile = np.asarray(profile_xy, dtype=np.float64)
    following = np.roll(profile, -1, axis=0)
    cross = profile[:, 0] * following[:, 1] - following[:, 0] * profile[:, 1]
    area_six = 3.0 * np.sum(cross)
    if abs(area_six) <= 1e-12:
        raise ValueError("polygon area must be non-zero")
    return np.asarray(
        [
            np.sum((profile[:, 0] + following[:, 0]) * cross) / area_six,
            np.sum((profile[:, 1] + following[:, 1]) * cross) / area_six,
        ]
    )


def _triangle_plane_segment(triangle: np.ndarray, z_mm: float, tolerance_mm: float) -> np.ndarray | None:
    distances = np.asarray(triangle[:, 2], dtype=np.float64) - z_mm
    if np.all(np.abs(distances) <= tolerance_mm):
        return None
    points: list[np.ndarray] = []
    for index in range(3):
        following = (index + 1) % 3
        start, end = triangle[index], triangle[following]
        d_start, d_end = distances[index], distances[following]
        if abs(d_start) <= tolerance_mm:
            points.append(np.asarray(start[:2], dtype=np.float64))
        if (d_start < -tolerance_mm and d_end > tolerance_mm) or (
            d_start > tolerance_mm and d_end < -tolerance_mm
        ):
            ratio = -d_start / (d_end - d_start)
            points.append(np.asarray(start[:2] + ratio * (end[:2] - start[:2]), dtype=np.float64))

    unique: list[np.ndarray] = []
    for point in points:
        if not any(np.linalg.norm(point - other) <= tolerance_mm for other in unique):
            unique.append(point)
    if len(unique) != 2 or np.linalg.norm(unique[0] - unique[1]) <= tolerance_mm:
        return None
    return np.asarray(unique)


def section_loops(mesh: StlMesh, z_mm: float, tolerance_mm: float) -> tuple[np.ndarray, ...]:
    """Intersect a triangle mesh with a Z plane and chain segments into closed loops."""
    if tolerance_mm <= 0:
        raise ValueError("tolerance_mm must be positive")
    raw_segments: list[np.ndarray] = []
    for triangle in np.asarray(mesh.triangles, dtype=np.float64):
        if np.all(np.abs(triangle[:, 2] - z_mm) <= tolerance_mm):
            raise ValueError("section plane is coplanar with a triangle; loop topology is ambiguous")
        segment = _triangle_plane_segment(triangle, z_mm, tolerance_mm)
        if segment is None:
            continue
        raw_segments.append(segment)

    points = np.asarray(raw_segments, dtype=np.float64).reshape(-1, 2)
    parents = list(range(len(points)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(first: int, second: int) -> None:
        root_first, root_second = find(first), find(second)
        if root_first != root_second:
            parents[root_second] = root_first

    buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
    for index, point in enumerate(points):
        cell = tuple(np.floor(point / tolerance_mm).astype(np.int64))
        for offset in product((-1, 0, 1), repeat=2):
            neighbour = (cell[0] + offset[0], cell[1] + offset[1])
            for other_index in buckets[neighbour]:
                if np.linalg.norm(point - points[other_index]) <= tolerance_mm:
                    union(index, other_index)
        buckets[cell].append(index)

    grouped_points: dict[int, list[np.ndarray]] = defaultdict(list)
    for index, point in enumerate(points):
        grouped_points[find(index)].append(point)
    representatives = {root: np.mean(group, axis=0) for root, group in grouped_points.items()}

    edge_keys: set[tuple[int, int]] = set()
    for index in range(len(raw_segments)):
        keys = [find(2 * index), find(2 * index + 1)]
        if keys[0] != keys[1]:
            edge_keys.add(tuple(sorted(keys)))

    adjacency: dict[int, list[int]] = defaultdict(list)
    for start, end in edge_keys:
        adjacency[start].append(end)
        adjacency[end].append(start)

    invalid_degrees = {vertex: len(neighbours) for vertex, neighbours in adjacency.items() if len(neighbours) != 2}
    if invalid_degrees:
        details = ", ".join(f"{vertex}:{degree}" for vertex, degree in sorted(invalid_degrees.items()))
        raise ValueError(f"section graph is not 2-regular; vertex degrees {details}")

    unused = set(edge_keys)
    loops: list[np.ndarray] = []
    while unused:
        first_edge = next(iter(unused))
        start, current = first_edge
        unused.remove(first_edge)
        chain = [start, current]
        previous = start
        while current != start:
            candidates = [
                neighbour
                for neighbour in adjacency[current]
                if tuple(sorted((current, neighbour))) in unused and neighbour != previous
            ]
            if len(candidates) != 1:
                raise ValueError("section graph left an ambiguous or open chain after 2-regular validation")
            following = candidates[0]
            unused.remove(tuple(sorted((current, following))))
            chain.append(following)
            previous, current = current, following
        if current != start or len(chain) < 4:
            raise ValueError("section graph contains an incomplete closed loop")
        profile = np.asarray([representatives[find(key)] for key in chain[:-1]], dtype=np.float64)
        if abs(polygon_area(profile)) <= tolerance_mm**2:
            raise ValueError("section graph contains a degenerate closed loop")
        loops.append(profile)
    return tuple(loops)


def _point_in_polygon(point_xy: np.ndarray, polygon_xy: np.ndarray) -> bool:
    x, y = point_xy
    inside = False
    following = np.roll(polygon_xy, -1, axis=0)
    for start, end in zip(polygon_xy, following, strict=True):
        crosses = (start[1] > y) != (end[1] > y)
        if crosses:
            intersection_x = (end[0] - start[0]) * (y - start[1]) / (end[1] - start[1]) + start[0]
            if x < intersection_x:
                inside = not inside
    return inside


def select_centered_d_loops(loops: tuple[np.ndarray, ...]) -> tuple[np.ndarray, np.ndarray]:
    """Select nested mating D contours, excluding centred flange and shell loops."""
    candidates: list[np.ndarray] = []
    for loop in loops:
        centroid = polygon_centroid(loop)
        extent = np.ptp(loop, axis=0)
        bounds_centre = (np.min(loop, axis=0) + np.max(loop, axis=0)) / 2.0
        if (
            np.all(np.abs(bounds_centre) <= 0.05)
            and abs(centroid[0]) <= 0.05
            and 10.0 <= extent[0] <= 20.0
            and 5.0 <= extent[1] <= 11.0
        ):
            candidates.append(loop)

    nested: list[tuple[float, float, np.ndarray, np.ndarray]] = []
    for outer in candidates:
        outer_area = abs(polygon_area(outer))
        for inner in candidates:
            inner_area = abs(polygon_area(inner))
            if outer_area <= inner_area:
                continue
            if all(_point_in_polygon(point, outer) for point in inner):
                nested.append((outer_area, inner_area, outer, inner))
    if not nested:
        raise ValueError("no nested centred D loops satisfy the mating-region bounds")
    _, _, outer, inner = max(nested, key=lambda item: (item[1], item[0]))
    return outer.copy(), inner.copy()
