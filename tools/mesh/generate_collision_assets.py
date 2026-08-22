"""Generate CAD-derived D-guide walls and the polygon32 hole fallback."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from tools.mesh.primitives import make_annular_sector, make_prism
from tools.mesh.section import polygon_area, polygon_centroid, section_loops, select_centered_d_loops
from tools.mesh.stl_binary import StlMesh, read_binary_stl, write_binary_stl


PROJECT_ROOT = Path(__file__).parents[2]
VISUAL_DIR = PROJECT_ROOT / "assets" / "visual"
COLLISION_DIR = PROJECT_ROOT / "assets" / "collision"
FEMALE_VISUAL = VISUAL_DIR / "dsub9_female_visual_centered.stl"
MALE_VISUAL = VISUAL_DIR / "dsub9_male_visual_centered.stl"

FEMALE_SECTION_Z_MM = 0.50
MALE_SECTION_Z_MM = 0.50
FEMALE_WALL_Z_MM = (0.0, 4.50)
MALE_WALL_Z_MM = (0.0, 4.00)
SECTION_TOLERANCE_MM = 1e-5

SECTOR_COUNT = 32
BORE_RADIUS_MM = 0.575
ENTRY_RADIUS_MM = 0.675
LOCAL_OUTER_RADIUS_MM = 1.0
ENTRANCE_DEPTH_MM = 0.25
MAIN_DEPTH_MM = 4.25
TOTAL_DEPTH_MM = ENTRANCE_DEPTH_MM + MAIN_DEPTH_MM

FALLBACK_HOLE_CENTRES_MM: tuple[tuple[float, float], ...] = (
    (-5.540, 1.420),
    (-2.770, 1.420),
    (0.000, 1.420),
    (2.770, 1.420),
    (5.540, 1.420),
    (-4.155, -1.420),
    (-1.385, -1.420),
    (1.385, -1.420),
    (4.155, -1.420),
)


def _ordered_profile(profile_xy: np.ndarray) -> np.ndarray:
    profile = np.asarray(profile_xy, dtype=np.float64)
    if polygon_area(profile) < 0:
        profile = profile[::-1].copy()
    maximum_x = np.max(profile[:, 0])
    candidates = np.flatnonzero(np.isclose(profile[:, 0], maximum_x, atol=1e-8, rtol=0.0))
    start = int(candidates[np.argmin(np.abs(profile[candidates, 1]))])
    return np.roll(profile, -start, axis=0)


def remove_collinear_points(profile_xy: np.ndarray, tolerance_mm: float) -> np.ndarray:
    """Remove only intermediate vertices within tolerance of their neighbour chord."""
    profile = np.asarray(profile_xy, dtype=np.float64)
    if profile.ndim != 2 or profile.shape[1:] != (2,) or len(profile) < 3:
        raise ValueError("profile must contain at least three XY points")
    if tolerance_mm <= 0:
        raise ValueError("tolerance_mm must be positive")
    previous = np.roll(profile, 1, axis=0)
    following = np.roll(profile, -1, axis=0)
    chord = following - previous
    chord_lengths = np.linalg.norm(chord, axis=1)
    cross = chord[:, 0] * (profile - previous)[:, 1] - chord[:, 1] * (profile - previous)[:, 0]
    distance = np.divide(
        np.abs(cross),
        chord_lengths,
        out=np.full(len(profile), np.inf),
        where=chord_lengths > 1e-12,
    )
    projection = np.einsum("ij,ij->i", profile - previous, following - profile)
    keep = (distance > tolerance_mm) | (projection < -tolerance_mm**2)
    simplified = profile[keep]
    if len(simplified) < 3:
        raise ValueError("collinear simplification removed the polygon")
    return simplified


def _arc_parameters(profile_xy: np.ndarray) -> np.ndarray:
    lengths = np.linalg.norm(np.roll(profile_xy, -1, axis=0) - profile_xy, axis=1)
    if np.any(lengths <= 1e-10):
        raise ValueError("D loop contains repeated adjacent points")
    cumulative = np.concatenate(([0.0], np.cumsum(lengths)))
    return cumulative / cumulative[-1]


def _align_vertices_by_arc_length(
    outer_xy: np.ndarray,
    inner_xy: np.ndarray,
) -> tuple[tuple[int, int], ...]:
    """Monotonically align real curve vertices using normalised arc position."""
    outer_parameters = _arc_parameters(outer_xy)
    inner_parameters = _arc_parameters(inner_xy)
    outer_count, inner_count = len(outer_xy), len(inner_xy)
    costs = np.full((outer_count + 1, inner_count + 1), np.inf)
    previous = np.full((outer_count + 1, inner_count + 1, 2), -1, dtype=np.int32)
    costs[0, 0] = 0.0
    gap_penalty = 0.01
    for outer_index in range(outer_count + 1):
        for inner_index in range(inner_count + 1):
            if outer_index == 0 and inner_index == 0:
                continue
            if outer_index == 0 or inner_index == 0:
                continue
            position_cost = abs(outer_parameters[outer_index] - inner_parameters[inner_index])
            choices: list[tuple[float, int, int]] = []
            if outer_index > 0 and inner_index > 0:
                choices.append((costs[outer_index - 1, inner_index - 1], outer_index - 1, inner_index - 1))
            if outer_index > 0 and inner_index > 0:
                choices.append(
                    (costs[outer_index - 1, inner_index] + gap_penalty, outer_index - 1, inner_index)
                )
            if inner_index > 0 and outer_index > 0:
                choices.append(
                    (costs[outer_index, inner_index - 1] + gap_penalty, outer_index, inner_index - 1)
                )
            best_cost, previous_outer, previous_inner = min(choices, key=lambda choice: choice[0])
            costs[outer_index, inner_index] = best_cost + position_cost
            previous[outer_index, inner_index] = (previous_outer, previous_inner)

    states = [(outer_count, inner_count)]
    while states[-1] != (0, 0):
        outer_index, inner_index = states[-1]
        prior = tuple(int(value) for value in previous[outer_index, inner_index])
        if prior == (-1, -1):
            raise ValueError("could not align D loops monotonically by arc length")
        states.append(prior)
    states.reverse()
    return tuple(states)


def _aligned_strip_profile(
    closed_outer: np.ndarray,
    closed_inner: np.ndarray,
    states: tuple[tuple[int, int], ...],
    start: int,
    end: int,
    tolerance_mm: float,
) -> np.ndarray:
    outer_start, inner_start = states[start]
    outer_end, inner_end = states[end]
    outer_path = closed_outer[outer_start : outer_end + 1]
    inner_path = closed_inner[inner_start : inner_end + 1][::-1]
    combined = np.vstack((outer_path, inner_path))
    deduplicated = [combined[0]]
    for point in combined[1:]:
        if np.linalg.norm(point - deduplicated[-1]) > tolerance_mm:
            deduplicated.append(point)
    if len(deduplicated) > 1 and np.linalg.norm(deduplicated[0] - deduplicated[-1]) <= tolerance_mm:
        deduplicated.pop()
    return remove_collinear_points(np.asarray(deduplicated), tolerance_mm)


def _is_valid_convex_profile(profile_xy: np.ndarray) -> bool:
    try:
        make_prism(profile_xy, 0.0, 1.0)
    except ValueError:
        return False
    return True


def _greedy_convex_partition(
    closed_outer: np.ndarray,
    closed_inner: np.ndarray,
    states: tuple[tuple[int, int], ...],
    tolerance_mm: float,
) -> tuple[np.ndarray, ...]:
    strip_count = len(states) - 1
    profiles: list[np.ndarray] = []
    start = 0
    while start < strip_count:
        best_end = start + 1
        best_profile = _aligned_strip_profile(
            closed_outer, closed_inner, states, start, best_end, tolerance_mm
        )
        if not _is_valid_convex_profile(best_profile):
            raise ValueError(f"individual D strip {start} is not a valid convex polygon")
        for end in range(start + 2, strip_count + 1):
            candidate = _aligned_strip_profile(closed_outer, closed_inner, states, start, end, tolerance_mm)
            if not _is_valid_convex_profile(candidate):
                break
            best_end, best_profile = end, candidate
        profiles.append(best_profile)
        start = best_end
    return tuple(profiles)


def build_d_wall_profiles(
    outer_xy: np.ndarray,
    inner_xy: np.ndarray,
    tolerance_mm: float = SECTION_TOLERANCE_MM,
) -> tuple[np.ndarray, ...]:
    """Decompose a CAD ring into non-overlapping convex strips without chord replacement."""
    outer = remove_collinear_points(_ordered_profile(outer_xy), tolerance_mm)
    inner = remove_collinear_points(_ordered_profile(inner_xy), tolerance_mm)
    closed_outer = np.vstack((outer, outer[0]))
    closed_inner = np.vstack((inner, inner[0]))
    states = _align_vertices_by_arc_length(outer, inner)
    best = _greedy_convex_partition(closed_outer, closed_inner, states, tolerance_mm)
    expected_area = abs(polygon_area(outer)) - abs(polygon_area(inner))
    generated_area = sum(abs(polygon_area(profile)) for profile in best)
    if not np.isclose(generated_area, expected_area, atol=2e-5, rtol=0.0):
        raise ValueError(
            f"D wall decomposition changed projected area: expected {expected_area}, got {generated_area}"
        )
    return best


def _translated_xy(mesh: StlMesh, offset_xy: tuple[float, float]) -> StlMesh:
    triangles = mesh.triangles.copy()
    triangles[:, :, :2] += np.asarray(offset_xy, dtype=np.float32)
    vertices = np.asarray(triangles, dtype=np.float64)
    normals = np.cross(vertices[:, 1] - vertices[:, 0], vertices[:, 2] - vertices[:, 0])
    normals /= np.linalg.norm(normals, axis=1)[:, np.newaxis]
    return StlMesh(normals=normals.astype(np.float32), triangles=triangles)


def _loop_metrics(profile_xy: np.ndarray) -> str:
    extent = np.ptp(profile_xy, axis=0)
    centroid = polygon_centroid(profile_xy)
    return (
        f"points={len(profile_xy)}, bbox={extent[0]:.6f}x{extent[1]:.6f} mm, "
        f"centroid=({centroid[0]:.6f},{centroid[1]:.6f}) mm, "
        f"area={abs(polygon_area(profile_xy)):.6f} mm^2"
    )


def _write_d_wall(
    prefix: str,
    mesh_path: Path,
    section_z_mm: float,
    wall_z_mm: tuple[float, float],
) -> tuple[list[Path], tuple[np.ndarray, np.ndarray]]:
    loops = section_loops(read_binary_stl(mesh_path), section_z_mm, SECTION_TOLERANCE_MM)
    outer, inner = select_centered_d_loops(loops)
    profiles = build_d_wall_profiles(outer, inner, SECTION_TOLERANCE_MM)
    paths: list[Path] = []
    for index, profile in enumerate(profiles):
        target = COLLISION_DIR / f"{prefix}_seg_{index:03d}.stl"
        write_binary_stl(target, make_prism(profile, *wall_z_mm))
        paths.append(target)
    print(f"{prefix}: z={section_z_mm:.3f} mm, outer {_loop_metrics(outer)}")
    print(f"{prefix}: z={section_z_mm:.3f} mm, inner {_loop_metrics(inner)}")
    minimum_area = min(abs(polygon_area(profile)) for profile in profiles)
    minimum_edge = min(
        np.linalg.norm(np.roll(profile, -1, axis=0) - profile, axis=1).min() for profile in profiles
    )
    print(
        f"{prefix}: {len(paths)} merged arc-paired convex wall prisms, "
        f"minimum_area={minimum_area:.9f} mm^2, minimum_edge={minimum_edge:.9f} mm"
    )
    return paths, (outer, inner)


def _write_fallback_holes() -> list[Path]:
    paths: list[Path] = []
    half_angle = np.pi / SECTOR_COUNT
    for hole_index, centre in enumerate(FALLBACK_HOLE_CENTRES_MM, start=1):
        for layer, nominal_radius, z0, z1 in (
            ("entry", ENTRY_RADIUS_MM, 0.0, ENTRANCE_DEPTH_MM),
            ("main", BORE_RADIUS_MM, ENTRANCE_DEPTH_MM, TOTAL_DEPTH_MM),
        ):
            corner_radius = nominal_radius / np.cos(half_angle)
            for sector_index in range(SECTOR_COUNT):
                centre_angle = 2.0 * np.pi * sector_index / SECTOR_COUNT
                mesh = make_annular_sector(
                    corner_radius,
                    LOCAL_OUTER_RADIUS_MM,
                    centre_angle - half_angle,
                    centre_angle + half_angle,
                    z0,
                    z1,
                )
                target = COLLISION_DIR / (
                    f"hole_fallback_32_h{hole_index:02d}_{layer}_s{sector_index:02d}.stl"
                )
                write_binary_stl(target, _translated_xy(mesh, centre))
                paths.append(target)
    error = BORE_RADIUS_MM * (1.0 / np.cos(np.pi / SECTOR_COUNT) - 1.0)
    print(
        f"hole_fallback_32: holes={len(FALLBACK_HOLE_CENTRES_MM)}, layers=2, "
        f"sectors/layer={SECTOR_COUNT}, parts={len(paths)}, radial_error={error:.9f} mm"
    )
    return paths


def generated_collision_paths() -> tuple[Path, ...]:
    """Enumerate only the collision assets owned by this generator."""
    patterns = ("d_guide_male_*.stl", "d_socket_female_*.stl", "hole_fallback_32_*.stl")
    return tuple(sorted(path for pattern in patterns for path in COLLISION_DIR.glob(pattern)))


def generate_collision_assets() -> tuple[Path, ...]:
    """Regenerate all Task 3 collision assets deterministically."""
    COLLISION_DIR.mkdir(parents=True, exist_ok=True)
    for existing in generated_collision_paths():
        existing.unlink()
    _write_d_wall("d_guide_male", MALE_VISUAL, MALE_SECTION_Z_MM, MALE_WALL_Z_MM)
    _write_d_wall("d_socket_female", FEMALE_VISUAL, FEMALE_SECTION_Z_MM, FEMALE_WALL_Z_MM)
    _write_fallback_holes()
    paths = generated_collision_paths()
    print(f"generated {len(paths)} collision STL parts in {COLLISION_DIR}")
    return paths


def main() -> None:
    generate_collision_assets()


if __name__ == "__main__":
    main()
