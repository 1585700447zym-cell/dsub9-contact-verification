from __future__ import annotations

from collections import Counter
from pathlib import Path
import shutil

import numpy as np
import pytest

from tools.mesh.generate_collision_assets import (
    ENTRANCE_DEPTH_MM,
    FALLBACK_HOLE_CENTRES_MM,
    MAIN_DEPTH_MM,
    generated_collision_paths,
)
import tools.mesh.generate_collision_assets as collision_assets
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


def _section_mesh(segments: tuple[tuple[tuple[float, float], tuple[float, float]], ...]) -> StlMesh:
    triangles = np.asarray(
        [[[a[0], a[1], 0.0], [b[0], b[1], 0.0], [a[0], a[1], 1.0]] for a, b in segments],
        dtype=np.float32,
    )
    return StlMesh(normals=np.zeros((len(triangles), 3), dtype=np.float32), triangles=triangles)


def _convex_hull(points_xy: np.ndarray) -> np.ndarray:
    points = sorted(set(map(tuple, np.asarray(points_xy, dtype=np.float64))))
    if len(points) < 3:
        raise ValueError("expected at least three unique XY points")

    def cross(origin, first, second):
        return (first[0] - origin[0]) * (second[1] - origin[1]) - (first[1] - origin[1]) * (
            second[0] - origin[0]
        )

    lower: list[tuple[float, float]] = []
    for point in points:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 1e-10:
            lower.pop()
        lower.append(point)
    upper: list[tuple[float, float]] = []
    for point in reversed(points):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 1e-10:
            upper.pop()
        upper.append(point)
    return np.asarray(lower[:-1] + upper[:-1])


def _line_intersection(a: np.ndarray, b: np.ndarray, c: np.ndarray, d: np.ndarray) -> np.ndarray:
    direction_ab = b - a
    direction_cd = d - c
    denominator = direction_ab[0] * direction_cd[1] - direction_ab[1] * direction_cd[0]
    if abs(denominator) <= 1e-14:
        return b
    offset = c - a
    fraction = (offset[0] * direction_cd[1] - offset[1] * direction_cd[0]) / denominator
    return a + fraction * direction_ab


def _convex_intersection(subject_xy: np.ndarray, clip_xy: np.ndarray) -> np.ndarray:
    output = np.asarray(subject_xy, dtype=np.float64)
    clip = np.asarray(clip_xy, dtype=np.float64)
    if polygon_area(output) < 0:
        output = output[::-1]
    if polygon_area(clip) < 0:
        clip = clip[::-1]
    for clip_start, clip_end in zip(clip, np.roll(clip, -1, axis=0), strict=True):
        if not len(output):
            break
        source = output
        result: list[np.ndarray] = []
        previous = source[-1]
        clip_direction = clip_end - clip_start
        previous_offset = previous - clip_start
        previous_inside = (
            clip_direction[0] * previous_offset[1] - clip_direction[1] * previous_offset[0] >= -1e-10
        )
        for current in source:
            current_offset = current - clip_start
            current_inside = (
                clip_direction[0] * current_offset[1] - clip_direction[1] * current_offset[0] >= -1e-10
            )
            if current_inside != previous_inside:
                result.append(_line_intersection(previous, current, clip_start, clip_end))
            if current_inside:
                result.append(current)
            previous, previous_inside = current, current_inside
        output = np.asarray(result)
    return output


def _point_in_polygon(point_xy: np.ndarray, polygon_xy: np.ndarray) -> bool:
    direction = np.roll(polygon_xy, -1, axis=0) - polygon_xy
    offsets = point_xy - polygon_xy
    crosses = direction[:, 0] * offsets[:, 1] - direction[:, 1] * offsets[:, 0]
    return bool(np.all(crosses >= -1e-5) or np.all(crosses <= 1e-5))


def _d_asset_profiles(prefix: str) -> list[np.ndarray]:
    profiles: list[np.ndarray] = []
    for path in generated_collision_paths():
        if not path.name.startswith(prefix):
            continue
        mesh = read_binary_stl(path)
        z0 = mesh.bounds.minimum[2]
        bottom_xy = mesh.triangles[np.isclose(mesh.triangles[:, :, 2], z0, atol=1e-6), :2]
        profiles.append(_convex_hull(bottom_xy))
    return profiles


def test_prism_rejects_repeated_adjacent_profile_points():
    """Accepting a zero-length profile edge would create degenerate faces."""
    profile = np.array([[0, 0], [1, 0], [1, 0], [0, 1]], dtype=float)
    with np.testing.assert_raises_regex(ValueError, "repeated adjacent"):
        make_prism(profile, 0.0, 1.0)


def test_prism_rejects_self_intersecting_pentagram():
    """A star can have consistent local turns while still crossing itself."""
    angles = np.deg2rad([90, 234, 18, 162, 306])
    pentagram = np.column_stack((np.cos(angles), np.sin(angles)))
    with pytest.raises(ValueError, match="self-intersecting"):
        make_prism(pentagram, 0.0, 1.0)


def test_basic_primitives_are_closed_non_degenerate_and_convex():
    """Incorrect face winding or a concave annular mesh breaks collision parts."""
    meshes = (
        make_prism(np.array([[0, 0], [1, 0], [0, 1]], dtype=float), 0.0, 0.5),
        make_prism(np.array([[0, 0], [2, 0], [2, 1], [0, 1]], dtype=float), 0.0, 0.5),
        make_annular_sector(0.575, 1.0, 0.0, np.pi / 16.0, 0.0, 0.25),
    )
    for mesh in meshes:
        assert mesh.triangles.shape[0] >= 12
        assert np.all(mesh.bounds.size > 0)
        assert _every_undirected_edge_occurs_twice(mesh)
        assert abs(_signed_tetrahedron_volumes(mesh).sum()) > 1e-8
        assert _is_convex(mesh)


def test_staging_validation_rejects_inside_out_mesh_with_negative_volume():
    outward = make_prism(np.array([[0, 0], [1, 0], [0, 1]], dtype=float), 0.0, 0.5)
    inside_out = StlMesh(
        normals=-outward.normals,
        triangles=outward.triangles[:, [0, 2, 1]],
    )

    with pytest.raises(ValueError, match="positive signed volume"):
        collision_assets._validate_collision_mesh(inside_out)


@pytest.mark.parametrize(
    "visual_name, expected_bbox, expected_area",
    [
        (
            "dsub9_female_visual_centered.stl",
            ([19.727337, 9.500000], [16.681988, 8.600000]),
            (175.159678, 128.406098),
        ),
        (
            "dsub9_male_visual_centered.stl",
            ([16.456263, 8.300000], [15.099202, 6.900000]),
            (121.656554, 91.623000),
        ),
    ],
)
def test_section_extraction_locks_actual_centered_d_loops(visual_name, expected_bbox, expected_area):
    """A flange, nominal rectangle, or symmetric substitute must fail exact CAD metrics."""
    mesh = read_binary_stl(VISUAL / visual_name)
    outer, inner = select_centered_d_loops(section_loops(mesh, z_mm=0.50, tolerance_mm=1e-5))
    for loop, bbox, area in zip((outer, inner), expected_bbox, expected_area, strict=True):
        np.testing.assert_allclose(np.ptp(loop, axis=0), bbox, atol=5e-4, rtol=0.0)
        np.testing.assert_allclose(abs(polygon_area(loop)), area, atol=2e-3, rtol=0.0)
        centroid = polygon_centroid(loop)
        assert abs(centroid[0]) < 1e-4
        assert 0.10 < centroid[1] < 0.25
        assert len(loop) > 8


def test_male_outer_d_profile_is_entirely_inside_female_inner_profile():
    """Bounds alone cannot prove the asymmetric mating contours have clearance."""
    female = select_centered_d_loops(
        section_loops(read_binary_stl(VISUAL / "dsub9_female_visual_centered.stl"), 0.50, 1e-5)
    )
    male = select_centered_d_loops(
        section_loops(read_binary_stl(VISUAL / "dsub9_male_visual_centered.stl"), 0.50, 1e-5)
    )
    assert all(_point_in_polygon(point, female[1]) for point in male[0])


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
    mesh = _section_mesh(segments)

    loops = section_loops(mesh, z_mm=0.0, tolerance_mm=1e-5)

    assert len(loops) == 1
    np.testing.assert_allclose(abs(polygon_area(loops[0])), 1.0, atol=2e-5)


def test_section_extraction_rejects_open_chain():
    mesh = _section_mesh((((0.0, 0.0), (1.0, 0.0)), ((1.0, 0.0), (1.0, 1.0))))
    with pytest.raises(ValueError, match="2-regular"):
        section_loops(mesh, 0.0, 1e-5)


def test_section_extraction_rejects_coplanar_triangle():
    triangles = np.asarray([[[0, 0, 0], [1, 0, 0], [0, 1, 0]]], dtype=np.float32)
    mesh = StlMesh(normals=np.zeros((1, 3), dtype=np.float32), triangles=triangles)
    with pytest.raises(ValueError, match="coplanar"):
        section_loops(mesh, 0.0, 1e-5)


def test_section_extraction_rejects_loops_that_share_an_edge():
    segments = (
        ((0, 0), (1, 0)), ((1, 0), (1, 1)), ((1, 1), (0, 1)), ((0, 1), (0, 0)),
        ((1, 0), (2, 0)), ((2, 0), (2, 1)), ((2, 1), (1, 1)), ((1, 1), (1, 0)),
    )
    with pytest.raises(ValueError, match="2-regular"):
        section_loops(_section_mesh(segments), 0.0, 1e-5)


def test_section_extraction_rejects_loops_that_only_share_a_vertex():
    segments = (
        ((0, 0), (1, 0)), ((1, 0), (1, 1)), ((1, 1), (0, 1)), ((0, 1), (0, 0)),
        ((1, 1), (2, 1)), ((2, 1), (2, 2)), ((2, 2), (1, 2)), ((1, 2), (1, 1)),
    )
    with pytest.raises(ValueError, match="2-regular"):
        section_loops(_section_mesh(segments), 0.0, 1e-5)


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


def test_d_collision_parts_cover_each_cad_ring_without_overlap_or_tiny_features():
    """Deleting strips or retaining tessellation slivers changes the projected wall."""
    cases = (
        ("d_guide_male_", "dsub9_male_visual_centered.stl", 80),
        ("d_socket_female_", "dsub9_female_visual_centered.stl", 50),
    )
    for prefix, visual_name, maximum_parts in cases:
        outer, inner = select_centered_d_loops(
            section_loops(read_binary_stl(VISUAL / visual_name), 0.50, 1e-5)
        )
        profiles = _d_asset_profiles(prefix)
        assert 1 < len(profiles) <= maximum_parts
        areas = np.asarray([abs(polygon_area(profile)) for profile in profiles])
        edges = np.concatenate(
            [np.linalg.norm(np.roll(profile, -1, axis=0) - profile, axis=1) for profile in profiles]
        )
        assert areas.min() >= 0.01
        assert edges.min() >= 0.01
        expected_ring_area = abs(polygon_area(outer)) - abs(polygon_area(inner))
        np.testing.assert_allclose(areas.sum(), expected_ring_area, atol=2e-4, rtol=0.0)
        for index, first in enumerate(profiles):
            for second in profiles[index + 1 :]:
                overlap = _convex_intersection(first, second)
                if len(overlap) >= 3:
                    assert abs(polygon_area(overlap)) <= 2e-7

        essential_vertices = np.vstack(
            (
                collision_assets.remove_collinear_points(outer, 1e-5),
                collision_assets.remove_collinear_points(inner, 1e-5),
            )
        )
        generated_vertices = np.vstack(profiles)
        for vertex in essential_vertices:
            assert np.min(np.linalg.norm(generated_vertices - vertex, axis=1)) <= 2e-5


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
        triangles = np.asarray(mesh.triangles, dtype=np.float64)
        expected_normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
        expected_normals /= np.linalg.norm(expected_normals, axis=1)[:, np.newaxis]
        np.testing.assert_allclose(mesh.normals, expected_normals, atol=2e-6, rtol=0.0, err_msg=path.name)


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


def test_generation_failure_leaves_existing_collision_assets_untouched(tmp_path, monkeypatch):
    """A CAD/mesh failure must not delete the last known-good collision set."""
    project_root = tmp_path / "project"
    collision_dir = project_root / "assets" / "collision"
    collision_dir.mkdir(parents=True)
    existing = collision_dir / "d_guide_male_seg_000.stl"
    existing.write_bytes(b"known-good")
    monkeypatch.setattr(collision_assets, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(collision_assets, "COLLISION_DIR", collision_dir)

    def fail_d_wall(*_args, **_kwargs):
        raise RuntimeError("injected generation failure")

    monkeypatch.setattr(collision_assets, "_write_d_wall", fail_d_wall)

    with pytest.raises(RuntimeError, match="injected generation failure"):
        collision_assets.generate_collision_assets()

    assert existing.read_bytes() == b"known-good"


def test_incomplete_staging_inventory_is_rejected_before_replacing_assets(tmp_path, monkeypatch):
    """Successful writer returns are insufficient unless the full inventory exists."""
    project_root = tmp_path / "project"
    collision_dir = project_root / "assets" / "collision"
    collision_dir.mkdir(parents=True)
    existing = collision_dir / "d_guide_male_seg_000.stl"
    existing.write_bytes(b"known-good")
    monkeypatch.setattr(collision_assets, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(collision_assets, "COLLISION_DIR", collision_dir)
    monkeypatch.setattr(collision_assets, "_write_d_wall", lambda *_args, **_kwargs: ([], ()))
    monkeypatch.setattr(collision_assets, "_write_fallback_holes", lambda *_args, **_kwargs: [])

    with pytest.raises(ValueError, match="collision asset inventory"):
        collision_assets.generate_collision_assets()

    assert existing.read_bytes() == b"known-good"


def test_invalid_staging_geometry_is_rejected_before_replacing_assets(tmp_path, monkeypatch):
    """A name-complete but corrupt staged set must not replace valid assets."""
    project_root = tmp_path / "project"
    collision_dir = project_root / "assets" / "collision"
    collision_dir.mkdir(parents=True)
    existing = collision_dir / "d_guide_male_seg_000.stl"
    existing.write_bytes(b"known-good")
    monkeypatch.setattr(collision_assets, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(collision_assets, "COLLISION_DIR", collision_dir)

    def write_corrupt_inventory(*args, **_kwargs):
        output_dir = args[-1]
        for name in collision_assets._expected_collision_names():
            (output_dir / name).write_bytes(b"not-a-binary-stl")
        return ([], ())

    monkeypatch.setattr(collision_assets, "_write_d_wall", write_corrupt_inventory)
    monkeypatch.setattr(collision_assets, "_write_fallback_holes", lambda *_args, **_kwargs: [])

    with pytest.raises(ValueError, match="invalid collision asset"):
        collision_assets.generate_collision_assets()

    assert existing.read_bytes() == b"known-good"


def test_staging_inventory_rejects_an_unexpected_directory(tmp_path):
    staging_dir = tmp_path / "staging"
    shutil.copytree(PROJECT_ROOT / "assets" / "collision", staging_dir)
    (staging_dir / "unexpected-directory").mkdir()

    with pytest.raises(ValueError, match="collision asset inventory"):
        collision_assets._validate_staging_inventory(staging_dir)


def test_staging_swap_failure_rolls_back_the_complete_previous_asset_set(tmp_path, monkeypatch):
    """Failure after backing up the target must restore every prior file byte-for-byte."""
    project_root = tmp_path / "project"
    collision_dir = project_root / "assets" / "collision"
    shutil.copytree(PROJECT_ROOT / "assets" / "collision", collision_dir)
    before = {path.name: path.read_bytes() for path in collision_dir.iterdir()}
    monkeypatch.setattr(collision_assets, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(collision_assets, "COLLISION_DIR", collision_dir)
    original_replace = Path.replace

    def fail_when_promoting_staging(source, target):
        if source.name.startswith(".collision-staging-") or source.parent.name.startswith(
            ".collision-staging-"
        ):
            raise OSError("injected staging promotion failure")
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", fail_when_promoting_staging)

    with pytest.raises(OSError, match="injected staging promotion failure"):
        collision_assets.generate_collision_assets()

    after = {path.name: path.read_bytes() for path in collision_dir.iterdir()}
    assert after == before


def test_rollback_failure_preserves_and_identifies_the_backup(tmp_path, monkeypatch):
    """A failed rollback must never let final cleanup erase the recoverable prior set."""
    project_root = tmp_path / "project"
    collision_dir = project_root / "assets" / "collision"
    collision_dir.mkdir(parents=True)
    existing = collision_dir / "d_guide_male_seg_000.stl"
    existing.write_bytes(b"known-good")
    monkeypatch.setattr(collision_assets, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(collision_assets, "COLLISION_DIR", collision_dir)

    def write_staged_marker(output_dir):
        (output_dir / "new.stl").write_bytes(b"staged")
        return ()

    monkeypatch.setattr(collision_assets, "_generate_into", write_staged_marker)
    monkeypatch.setattr(collision_assets, "_validate_staging_inventory", lambda _directory: ())
    original_replace = Path.replace

    def fail_promotion_and_rollback(source, target):
        if source.name.startswith(".collision-staging-"):
            raise OSError("injected staging promotion failure")
        if source.name.startswith(".collision-backup-"):
            raise OSError("injected rollback failure")
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", fail_promotion_and_rollback)

    with pytest.raises(RuntimeError, match="previous assets remain at") as captured:
        collision_assets.generate_collision_assets()

    backups = list(collision_dir.parent.glob(".collision-backup-*"))
    assert len(backups) == 1
    assert str(backups[0]) in str(captured.value)
    assert (backups[0] / existing.name).read_bytes() == b"known-good"
    assert not list(collision_dir.parent.glob(".collision-staging-*"))


def test_target_with_unowned_files_is_rejected_before_generation(tmp_path, monkeypatch):
    """Directory-level replacement may only operate on the generator-owned asset directory."""
    project_root = tmp_path / "project"
    collision_dir = project_root / "assets" / "collision"
    collision_dir.mkdir(parents=True)
    (collision_dir / "notes.txt").write_text("preserve me", encoding="utf-8")
    monkeypatch.setattr(collision_assets, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(collision_assets, "COLLISION_DIR", collision_dir)

    with pytest.raises(ValueError, match="not owned by this generator"):
        collision_assets.generate_collision_assets()

    assert (collision_dir / "notes.txt").read_text(encoding="utf-8") == "preserve me"


def test_collision_target_must_resolve_inside_the_project_workspace(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    collision_dir = tmp_path / "outside" / "collision"
    monkeypatch.setattr(collision_assets, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(collision_assets, "COLLISION_DIR", collision_dir)

    with pytest.raises(ValueError, match="outside project workspace"):
        collision_assets.generate_collision_assets()

    assert not collision_dir.exists()


def test_collision_target_must_be_the_exact_project_collision_directory(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    collision_dir = project_root / "temporary" / "collision"
    monkeypatch.setattr(collision_assets, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(collision_assets, "COLLISION_DIR", collision_dir)

    with pytest.raises(ValueError, match="must be the project assets/collision directory"):
        collision_assets.generate_collision_assets()

    assert not collision_dir.exists()


def test_temporary_cleanup_refuses_a_path_outside_the_collision_parent(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    collision_dir = project_root / "assets" / "collision"
    unsafe = project_root / ".collision-staging-do-not-remove"
    unsafe.mkdir(parents=True)
    monkeypatch.setattr(collision_assets, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(collision_assets, "COLLISION_DIR", collision_dir)

    with pytest.raises(ValueError, match="refusing to remove unsafe temporary directory"):
        collision_assets._remove_temporary_directory(unsafe, ".collision-staging-")

    assert unsafe.is_dir()
