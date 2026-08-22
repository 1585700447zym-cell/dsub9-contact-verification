from __future__ import annotations

from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from tools.mesh.generate_collision_assets import (
    ENTRANCE_DEPTH_MM,
    FALLBACK_HOLE_CENTRES_MM,
    MAIN_DEPTH_MM,
    generated_collision_paths,
)
from tools.mesh.primitives import make_annular_sector, make_prism
from tools.mesh.section import (
    polygon_area,
    polygon_centroid,
    section_loops,
    select_centered_d_loops,
)
from tools.mesh.stl_binary import StlMesh, read_binary_stl


PROJECT_ROOT = Path(__file__).parents[2]
VISUAL = PROJECT_ROOT / "assets" / "visual"


def _vertex_key(vertex: np.ndarray) -> tuple[float, float, float]:
    return tuple(float(value) for value in np.round(vertex, decimals=5))


def _every_undirected_edge_occurs_twice(mesh: StlMesh) -> bool:
    edges: Counter[tuple[tuple[float, ...], tuple[float, ...]]] = Counter()
    for triangle in mesh.triangles:
        for start, end in zip(triangle, np.roll(triangle, -1, axis=0), strict=True):
            a, b = _vertex_key(start), _vertex_key(end)
            edges[tuple(sorted((a, b)))] += 1
    return bool(edges) and set(edges.values()) == {2}


def _signed_tetrahedron_volumes(mesh: StlMesh) -> np.ndarray:
    triangles = np.asarray(mesh.triangles, dtype=np.float64)
    return np.einsum(
        "ij,ij->i",
        triangles[:, 0],
        np.cross(triangles[:, 1], triangles[:, 2]),
    ) / 6.0


def _is_convex(mesh: StlMesh, tolerance_mm: float = 2e-5) -> bool:
    triangles = np.asarray(mesh.triangles, dtype=np.float64)
    vertices = np.unique(triangles.reshape(-1, 3), axis=0)
    centre = vertices.mean(axis=0)
    for triangle in triangles:
        normal = np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])
        if np.dot(normal, centre - triangle[0]) > 0:
            normal = -normal
        if np.max((vertices - triangle[0]) @ normal) > tolerance_mm * np.linalg.norm(normal):
            return False
    return True


def test_prism_rejects_repeated_adjacent_profile_points():
    """Accepting a zero-length profile edge would create degenerate faces."""
    profile = np.array([[0, 0], [1, 0], [1, 0], [0, 1]], dtype=float)
    with np.testing.assert_raises_regex(ValueError, "repeated adjacent"):
        make_prism(profile, 0.0, 1.0)


def test_basic_primitives_are_closed_non_degenerate_and_convex():
    """Incorrect face winding or a concave annular mesh breaks collision parts."""
    meshes = (
        make_prism(np.array([[0, 0], [2, 0], [2, 1], [0, 1]], dtype=float), 0.0, 0.5),
        make_annular_sector(0.575, 1.0, 0.0, np.pi / 16.0, 0.0, 0.25),
    )
    for mesh in meshes:
        assert mesh.triangles.shape[0] >= 12
        assert np.all(mesh.bounds.size > 0)
        assert _every_undirected_edge_occurs_twice(mesh)
        assert abs(_signed_tetrahedron_volumes(mesh).sum()) > 1e-8
        assert _is_convex(mesh)


def test_section_extraction_finds_actual_centered_female_d_loops():
    """Selecting a flange or replacing CAD arcs with a nominal box must fail."""
    mesh = read_binary_stl(VISUAL / "dsub9_female_visual_centered.stl")
    loops = section_loops(mesh, z_mm=0.50, tolerance_mm=1e-5)
    outer, inner = select_centered_d_loops(loops)
    for loop in (outer, inner):
        extent = np.ptp(loop, axis=0)
        bounds_centre = (loop.min(axis=0) + loop.max(axis=0)) / 2.0
        assert abs(polygon_centroid(loop)[0]) < 0.05
        assert np.all(np.abs(bounds_centre) < 0.05)
        assert 10.0 <= extent[0] <= 20.0
        assert 5.0 <= extent[1] <= 11.0
    assert abs(polygon_area(outer)) > abs(polygon_area(inner))
    assert len(outer) > 8 and len(inner) > 8


def test_section_extraction_snaps_endpoints_by_distance_not_rounding_bin():
    """Endpoints inside tolerance must join even when they straddle a grid boundary."""
    almost_left = 1.0000049
    almost_right = 1.0000051
    segments = (
        ((0.0, 0.0), (almost_left, 0.0)),
        ((almost_right, 0.0), (1.0, 1.0)),
        ((1.0, 1.0), (0.0, 1.0)),
        ((0.0, 1.0), (0.0, 0.0)),
    )
    triangles = np.asarray(
        [[[a[0], a[1], 0.0], [b[0], b[1], 0.0], [a[0], a[1], 1.0]] for a, b in segments],
        dtype=np.float32,
    )
    mesh = StlMesh(normals=np.zeros((4, 3), dtype=np.float32), triangles=triangles)

    loops = section_loops(mesh, z_mm=0.0, tolerance_mm=1e-5)

    assert len(loops) == 1
    np.testing.assert_allclose(abs(polygon_area(loops[0])), 1.0, atol=2e-5)


def test_d_loop_selection_rejects_centred_intersecting_non_nested_profiles():
    """A centred centroid alone must not classify intersecting shells as nested."""
    horizontal = np.asarray([[-9.5, -3], [9.5, -3], [9.5, 3], [-9.5, 3]], dtype=float)
    vertical = np.asarray([[-6, -4.5], [6, -4.5], [6, 4.5], [-6, 4.5]], dtype=float)

    with pytest.raises(ValueError, match="no nested centred D loops"):
        select_centered_d_loops((horizontal, vertical))


def test_generated_asset_inventory_represents_both_d_walls_and_all_hole_layers():
    """Dropping a hole, depth layer, sector, or either D wall must be detected."""
    paths = generated_collision_paths()
    names = [path.name for path in paths]
    assert any(name.startswith("d_guide_male_") for name in names)
    assert any(name.startswith("d_socket_female_") for name in names)
    assert len(FALLBACK_HOLE_CENTRES_MM) == 9
    entrance = [name for name in names if name.startswith("hole_fallback_32_") and "_entry_" in name]
    main = [name for name in names if name.startswith("hole_fallback_32_") and "_main_" in name]
    assert len(entrance) == 9 * 32
    assert len(main) == 9 * 32
    assert ENTRANCE_DEPTH_MM == 0.25
    assert MAIN_DEPTH_MM == 4.25


def test_each_generated_collision_part_is_closed_non_degenerate_and_convex():
    """Every STL is independently usable as one convex collision component."""
    paths = generated_collision_paths()
    assert paths
    for path in paths:
        assert path.is_file(), path
        mesh = read_binary_stl(path)
        assert mesh.triangles.shape[0] >= 12, path.name
        assert np.all(mesh.bounds.size > 0), path.name
        assert _every_undirected_edge_occurs_twice(mesh), path.name
        assert abs(_signed_tetrahedron_volumes(mesh).sum()) > 1e-8, path.name
        assert _is_convex(mesh), path.name


def test_fallback_assets_encode_documented_radii_and_total_depth():
    """Wrong entrance/main radii or overlapping axial layers change clearance."""
    paths = generated_collision_paths()
    entry = read_binary_stl(next(path for path in paths if "hole_fallback_32_h01_entry_s00" in path.name))
    main = read_binary_stl(next(path for path in paths if "hole_fallback_32_h01_main_s00" in path.name))
    centre = np.asarray(FALLBACK_HOLE_CENTRES_MM[0], dtype=float)

    for mesh, nominal_inner_radius, z_bounds in (
        (entry, 0.675, (0.0, 0.25)),
        (main, 0.575, (0.25, 4.50)),
    ):
        vertices = np.unique(mesh.triangles.reshape(-1, 3), axis=0)
        radii = np.linalg.norm(vertices[:, :2] - centre, axis=1)
        expected_corner_radius = nominal_inner_radius / np.cos(np.pi / 32.0)
        np.testing.assert_allclose(radii.min(), expected_corner_radius, atol=2e-5)
        assert expected_corner_radius - nominal_inner_radius < 0.0035
        np.testing.assert_allclose(mesh.bounds.minimum[2], z_bounds[0], atol=2e-5)
        np.testing.assert_allclose(mesh.bounds.maximum[2], z_bounds[1], atol=2e-5)


def test_32_sided_hole_error_is_below_three_microns():
    """Using fewer sides can consume too much of the 0.075 mm radial gap."""
    radius = 0.575
    error = radius * (1.0 / np.cos(np.pi / 32.0) - 1.0)
    assert error < 0.003
