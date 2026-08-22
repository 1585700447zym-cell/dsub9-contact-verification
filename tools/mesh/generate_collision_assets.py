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


def _arc_parameters(profile_xy: np.ndarray) -> np.ndarray:
    lengths = np.linalg.norm(np.roll(profile_xy, -1, axis=0) - profile_xy, axis=1)
    if np.any(lengths <= 1e-10):
        raise ValueError("D loop contains repeated adjacent points")
    cumulative = np.concatenate(([0.0], np.cumsum(lengths)))
    return cumulative / cumulative[-1]


def _sample_closed_profile(profile_xy: np.ndarray, parameters: np.ndarray) -> np.ndarray:
    cumulative = _arc_parameters(profile_xy)
    closed = np.vstack((profile_xy, profile_xy[0]))
    return np.column_stack(
        (
            np.interp(parameters, cumulative, closed[:, 0]),
            np.interp(parameters, cumulative, closed[:, 1]),
        )
    )


def pair_loops_by_arc_length(
    outer_xy: np.ndarray,
    inner_xy: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Pair nested profiles at the union of both source vertex arc positions."""
    outer = _ordered_profile(outer_xy)
    inner = _ordered_profile(inner_xy)
    parameters = np.unique(
        np.round(
            np.concatenate((_arc_parameters(outer)[:-1], _arc_parameters(inner)[:-1])),
            decimals=12,
        )
    )
    return _sample_closed_profile(outer, parameters), _sample_closed_profile(inner, parameters)


def _translated_xy(mesh: StlMesh, offset_xy: tuple[float, float]) -> StlMesh:
    triangles = mesh.triangles.copy()
    triangles[:, :, :2] += np.asarray(offset_xy, dtype=np.float32)
    return StlMesh(normals=mesh.normals.copy(), triangles=triangles)


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
    paired_outer, paired_inner = pair_loops_by_arc_length(outer, inner)
    paths: list[Path] = []
    for index in range(len(paired_outer)):
        following = (index + 1) % len(paired_outer)
        profile = np.asarray(
            [
                paired_outer[index],
                paired_outer[following],
                paired_inner[following],
                paired_inner[index],
            ]
        )
        target = COLLISION_DIR / f"{prefix}_seg_{index:03d}.stl"
        write_binary_stl(target, make_prism(profile, *wall_z_mm))
        paths.append(target)
    print(f"{prefix}: z={section_z_mm:.3f} mm, outer {_loop_metrics(outer)}")
    print(f"{prefix}: z={section_z_mm:.3f} mm, inner {_loop_metrics(inner)}")
    print(f"{prefix}: {len(paths)} arc-paired convex wall prisms")
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
