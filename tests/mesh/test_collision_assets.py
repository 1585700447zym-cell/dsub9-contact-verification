from __future__ import annotations

from collections import Counter
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

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


def _windows_acl_summary(path: Path) -> tuple[bool, tuple[tuple[str, int, int, int], ...]]:
    win32security = pytest.importorskip("win32security")
    descriptor = win32security.GetNamedSecurityInfo(
        str(path),
        win32security.SE_FILE_OBJECT,
        win32security.DACL_SECURITY_INFORMATION,
    )
    control, _revision = descriptor.GetSecurityDescriptorControl()
    dacl = descriptor.GetSecurityDescriptorDacl()
    aces: list[tuple[str, int, int, int]] = []
    for index in range(dacl.GetAceCount()):
        header, mask, sid = dacl.GetAce(index)
        aces.append((win32security.ConvertSidToStringSid(sid), header[0], header[1], mask))
    protected = bool(control & win32security.SE_DACL_PROTECTED)
    return protected, tuple(aces)


def _make_windows_acl_fixture(tmp_path: Path, child_count: int) -> tuple[Path, Path, tuple[Path, ...], Path]:
    icacls_text = shutil.which("icacls.exe")
    if icacls_text is None:
        pytest.skip("Windows icacls.exe is unavailable")
    icacls = Path(icacls_text)
    parent = tmp_path / "acl-parent"
    parent.mkdir()
    subprocess.run(
        [
            str(icacls),
            str(parent),
            "/grant",
            "*S-1-1-0:(OI)(CI)R",
            "*S-1-5-11:(OI)(CI)R",
            "*S-1-5-4:(CI)R",
            "*S-1-2-0:(OI)R",
            "*S-1-5-2:R",
            "/Q",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    staging = Path(tempfile.mkdtemp(prefix=".collision-staging-", dir=parent))
    children = tuple(staging / f"dummy_{index:03d}.stl" for index in range(child_count))
    for child in children:
        child.write_bytes(b"acl-probe")
    subprocess.run(
        [str(icacls), str(staging), "/inheritance:d", "/T", "/Q"],
        check=True,
        capture_output=True,
        text=True,
    )
    return parent, staging, children, icacls


def _forge_unprotected_system_read_dacl(path: Path) -> None:
    """Create a real malformed DACL that the old postcondition mistakes for inherited access."""
    win32api = pytest.importorskip("win32api")
    win32con = pytest.importorskip("win32con")
    win32security = pytest.importorskip("win32security")
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try:
        owner_sid = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
    finally:
        token.Close()
    dacl = win32security.ACL()
    dacl.AddAccessAllowedAceEx(win32security.ACL_REVISION, 0, 0x001F01FF, owner_sid)
    dacl.AddAccessAllowedAceEx(
        win32security.ACL_REVISION,
        win32security.INHERITED_ACE,
        0x00120089,
        win32security.ConvertStringSidToSid("S-1-5-18"),
    )
    descriptor = win32security.SECURITY_DESCRIPTOR()
    descriptor.SetSecurityDescriptorDacl(True, dacl, False)
    descriptor.SetSecurityDescriptorControl(win32security.SE_DACL_PROTECTED, 0)
    win32security.SetFileSecurity(
        str(path), win32security.DACL_SECURITY_INFORMATION, descriptor
    )


def _add_inherited_everyone_read_deny(path: Path) -> None:
    """Preserve every normalized ALLOW while inserting one effective inherited read DENY."""
    win32api = pytest.importorskip("win32api")
    win32con = pytest.importorskip("win32con")
    win32security = pytest.importorskip("win32security")
    descriptor = win32security.GetNamedSecurityInfo(
        str(path),
        win32security.SE_FILE_OBJECT,
        win32security.DACL_SECURITY_INFORMATION,
    )
    original = descriptor.GetSecurityDescriptorDacl()
    entries = tuple(original.GetAce(index) for index in range(original.GetAceCount()))
    replacement = win32security.ACL()
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try:
        owner_sid = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
    finally:
        token.Close()
    replacement.AddAccessAllowedAceEx(
        win32security.ACL_REVISION, 0, 0x001F01FF, owner_sid
    )
    for header, mask, sid in entries:
        if not header[1] & win32security.INHERITED_ACE:
            replacement.AddAccessAllowedAceEx(
                win32security.ACL_REVISION, header[1], mask, sid
            )
    replacement.AddAccessDeniedAceEx(
        win32security.ACL_REVISION,
        win32security.INHERITED_ACE,
        0x00120089,
        win32security.ConvertStringSidToSid("S-1-1-0"),
    )
    for header, mask, sid in entries:
        if header[1] & win32security.INHERITED_ACE:
            replacement.AddAccessAllowedAceEx(
                win32security.ACL_REVISION, header[1], mask, sid
            )
    replacement_descriptor = win32security.SECURITY_DESCRIPTOR()
    replacement_descriptor.SetSecurityDescriptorDacl(True, replacement, False)
    replacement_descriptor.SetSecurityDescriptorControl(win32security.SE_DACL_PROTECTED, 0)
    win32security.SetFileSecurity(
        str(path), win32security.DACL_SECURITY_INFORMATION, replacement_descriptor
    )


def _rewrite_simple_windows_dacl(path: Path, rewrite) -> None:
    """Rewrite an isolated fixture DACL while preserving simple ALLOW/DENY ACE data."""
    win32security = pytest.importorskip("win32security")
    descriptor = win32security.GetNamedSecurityInfo(
        str(path),
        win32security.SE_FILE_OBJECT,
        win32security.DACL_SECURITY_INFORMATION,
    )
    original = descriptor.GetSecurityDescriptorDacl()
    entries = []
    for index in range(original.GetAceCount()):
        header, mask, sid = original.GetAce(index)
        assert header[0] in (
            win32security.ACCESS_ALLOWED_ACE_TYPE,
            win32security.ACCESS_DENIED_ACE_TYPE,
        )
        entries.append((header[0], header[1], mask, sid))

    replacement = win32security.ACL()
    for ace_type, flags, mask, sid in rewrite(tuple(entries)):
        if ace_type == win32security.ACCESS_ALLOWED_ACE_TYPE:
            replacement.AddAccessAllowedAceEx(
                win32security.ACL_REVISION, flags, mask, sid
            )
        elif ace_type == win32security.ACCESS_DENIED_ACE_TYPE:
            replacement.AddAccessDeniedAceEx(
                win32security.ACL_REVISION, flags, mask, sid
            )
        else:  # pragma: no cover - fixture contract guard
            raise AssertionError(f"unsupported fixture ACE type: {ace_type}")

    replacement_descriptor = win32security.SECURITY_DESCRIPTOR()
    replacement_descriptor.SetSecurityDescriptorDacl(True, replacement, False)
    replacement_descriptor.SetSecurityDescriptorControl(
        win32security.SE_DACL_PROTECTED, 0
    )
    win32security.SetFileSecurity(
        str(path), win32security.DACL_SECURITY_INFORMATION, replacement_descriptor
    )


def _append_inherited_read_allow(path: Path, sid_text: str) -> None:
    win32security = pytest.importorskip("win32security")
    sid = win32security.ConvertStringSidToSid(sid_text)

    def append(entries):
        return (
            *entries,
            (
                win32security.ACCESS_ALLOWED_ACE_TYPE,
                win32security.INHERITED_ACE,
                0x00120089,
                sid,
            ),
        )

    _rewrite_simple_windows_dacl(path, append)


def _make_inherited_read_allow_effective(path: Path, sid_text: str) -> None:
    win32security = pytest.importorskip("win32security")

    def clear_inherit_only(entries):
        changed = False
        rewritten = []
        for ace_type, flags, mask, sid in entries:
            if (
                win32security.ConvertSidToStringSid(sid) == sid_text
                and flags & win32security.INHERITED_ACE
                and flags & win32security.INHERIT_ONLY_ACE
                and mask & 0x1
            ):
                flags &= ~win32security.INHERIT_ONLY_ACE
                changed = True
            rewritten.append((ace_type, flags, mask, sid))
        assert changed, sid_text
        return tuple(rewritten)

    _rewrite_simple_windows_dacl(path, clear_inherit_only)


def _remove_read_propagation_flags(path: Path, sid_text: str) -> None:
    win32security = pytest.importorskip("win32security")

    def remove_flags(entries):
        changed = False
        rewritten = []
        for ace_type, flags, mask, sid in entries:
            if (
                win32security.ConvertSidToStringSid(sid) == sid_text
                and flags & win32security.INHERITED_ACE
                and not flags & win32security.INHERIT_ONLY_ACE
                and mask & 0x1
            ):
                flags &= ~(
                    win32security.OBJECT_INHERIT_ACE
                    | win32security.CONTAINER_INHERIT_ACE
                )
                changed = True
            rewritten.append((ace_type, flags, mask, sid))
        assert changed, sid_text
        return tuple(rewritten)

    _rewrite_simple_windows_dacl(path, remove_flags)


def _write_acl_probe_children(output_dir: Path, child_count: int = 696) -> tuple[Path, ...]:
    children = tuple(output_dir / f"dummy_{index:03d}.stl" for index in range(child_count))
    for child in children:
        child.write_bytes(b"acl-probe")
    return children


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


def test_completed_backup_move_that_then_raises_is_rolled_back(tmp_path, monkeypatch):
    """Post-move Windows/wrapper errors must not strand the old set under a hidden backup."""
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

    def complete_backup_move_then_raise(source, target):
        if source == collision_dir:
            original_replace(source, target)
            raise OSError("injected post-backup-move failure")
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", complete_backup_move_then_raise)

    with pytest.raises(OSError, match="injected post-backup-move failure"):
        collision_assets.generate_collision_assets()

    assert existing.read_bytes() == b"known-good"
    assert not list(collision_dir.parent.glob(".collision-backup-*"))


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


def test_cleanup_failure_cannot_mask_the_preserved_backup_after_rollback_failure(
    tmp_path, monkeypatch
):
    """The final exception must retain recovery information across all three failures."""
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
    original_remove = collision_assets._remove_temporary_directory

    def fail_staging_cleanup(path, prefix):
        if path.name.startswith(".collision-staging-"):
            raise OSError("injected staging cleanup failure")
        return original_remove(path, prefix)

    monkeypatch.setattr(collision_assets, "_remove_temporary_directory", fail_staging_cleanup)

    with pytest.raises(RuntimeError, match="previous assets remain at") as captured:
        collision_assets.generate_collision_assets()

    backups = list(collision_dir.parent.glob(".collision-backup-*"))
    assert len(backups) == 1
    assert str(backups[0]) in str(captured.value)
    assert "injected staging cleanup failure" in str(captured.value)
    assert (backups[0] / existing.name).read_bytes() == b"known-good"


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


def test_compound_access_ace_type_is_rejected_fail_closed(tmp_path):
    """A synthetic 0x04 access-control ACE must never be silently skipped."""
    with pytest.raises(PermissionError, match="unsupported DACL ACE type 4"):
        collision_assets._require_supported_dacl_ace_type(0x04, tmp_path / "synthetic")


@pytest.mark.skipif(os.name != "nt", reason="Windows DACL inheritance behavior")
def test_recursive_normalizer_applies_known_parent_read_ace_to_all_696_children(
    tmp_path, monkeypatch
):
    """Inspect an isolated real DACL tree without mutating production collision assets."""
    win32security = pytest.importorskip("win32security")
    parent, staging, children, _icacls = _make_windows_acl_fixture(tmp_path, 696)
    monkeypatch.setattr(collision_assets, "COLLISION_DIR", parent / "collision")
    assert _windows_acl_summary(staging)[0]
    assert all(_windows_acl_summary(child)[0] for child in children)

    collision_assets._normalize_staging_permissions(staging)

    for path in (staging, *children):
        protected, aces = _windows_acl_summary(path)
        assert not protected, path
        for expected_sid in ("S-1-1-0", "S-1-5-11"):
            assert any(
                sid == expected_sid
                and ace_type == win32security.ACCESS_ALLOWED_ACE_TYPE
                and flags & win32security.INHERITED_ACE
                and mask & 0x1
                for sid, ace_type, flags, mask in aces
            ), (path, expected_sid)

    _protected, staging_aces = _windows_acl_summary(staging)
    assert any(
        sid == "S-1-5-4"
        and flags & win32security.CONTAINER_INHERIT_ACE
        and not flags & win32security.INHERIT_ONLY_ACE
        for sid, _ace_type, flags, _mask in staging_aces
    )
    assert any(
        sid == "S-1-2-0"
        and flags & win32security.OBJECT_INHERIT_ACE
        and flags & win32security.INHERIT_ONLY_ACE
        for sid, _ace_type, flags, _mask in staging_aces
    )
    assert not any(sid == "S-1-5-2" for sid, *_rest in staging_aces)
    for child in children:
        _protected, child_aces = _windows_acl_summary(child)
        child_sids = {sid for sid, *_rest in child_aces}
        assert "S-1-2-0" in child_sids
        assert "S-1-5-4" not in child_sids
        assert "S-1-5-2" not in child_sids


@pytest.mark.skipif(os.name != "nt", reason="Windows exact ACE propagation behavior")
def test_parent_noninheritable_read_sid_forged_on_child_is_rejected(
    tmp_path, monkeypatch
):
    """A parent's object-local ALLOW is not authority for an inherited child ALLOW."""
    parent, staging, children, _icacls = _make_windows_acl_fixture(tmp_path, 1)
    monkeypatch.setattr(collision_assets, "COLLISION_DIR", parent / "collision")
    real_run = subprocess.run

    def reset_then_forge_noninheritable_sid(args, **kwargs):
        completed = real_run(args, **kwargs)
        _append_inherited_read_allow(children[0], "S-1-5-2")
        return completed

    monkeypatch.setattr(
        collision_assets.subprocess, "run", reset_then_forge_noninheritable_sid
    )

    with pytest.raises(PermissionError, match="parent-inherited read DACL semantics"):
        collision_assets._normalize_staging_permissions(staging)


@pytest.mark.skipif(os.name != "nt", reason="Windows exact ACE propagation behavior")
def test_container_only_parent_read_sid_forged_on_file_is_rejected(
    tmp_path, monkeypatch
):
    """A CI-only parent ACE must never be accepted as inherited file access."""
    parent, staging, children, _icacls = _make_windows_acl_fixture(tmp_path, 1)
    monkeypatch.setattr(collision_assets, "COLLISION_DIR", parent / "collision")
    real_run = subprocess.run

    def reset_then_forge_container_only_sid(args, **kwargs):
        completed = real_run(args, **kwargs)
        _append_inherited_read_allow(children[0], "S-1-5-4")
        return completed

    monkeypatch.setattr(
        collision_assets.subprocess, "run", reset_then_forge_container_only_sid
    )

    with pytest.raises(PermissionError, match="parent-inherited read DACL semantics"):
        collision_assets._normalize_staging_permissions(staging)


@pytest.mark.skipif(os.name != "nt", reason="Windows exact ACE propagation behavior")
def test_object_only_parent_read_sid_made_effective_on_root_is_rejected(
    tmp_path, monkeypatch
):
    """An OI-only parent ACE is inherit-only on a container, not root access."""
    parent, staging, _children, _icacls = _make_windows_acl_fixture(tmp_path, 1)
    monkeypatch.setattr(collision_assets, "COLLISION_DIR", parent / "collision")
    real_run = subprocess.run

    def reset_then_make_object_only_sid_effective(args, **kwargs):
        completed = real_run(args, **kwargs)
        _make_inherited_read_allow_effective(staging, "S-1-2-0")
        return completed

    monkeypatch.setattr(
        collision_assets.subprocess,
        "run",
        reset_then_make_object_only_sid_effective,
    )

    with pytest.raises(PermissionError, match="parent-inherited read DACL semantics"):
        collision_assets._normalize_staging_permissions(staging)


@pytest.mark.skipif(os.name != "nt", reason="Windows exact ACE propagation behavior")
def test_staging_root_missing_future_read_propagation_flags_is_rejected(
    tmp_path, monkeypatch
):
    """Current root read is insufficient if a future child would lose parent read access."""
    parent, staging, _children, _icacls = _make_windows_acl_fixture(tmp_path, 1)
    monkeypatch.setattr(collision_assets, "COLLISION_DIR", parent / "collision")
    real_run = subprocess.run

    def reset_then_remove_propagation(args, **kwargs):
        completed = real_run(args, **kwargs)
        _remove_read_propagation_flags(staging, "S-1-1-0")
        return completed

    monkeypatch.setattr(
        collision_assets.subprocess, "run", reset_then_remove_propagation
    )

    with pytest.raises(PermissionError, match="parent-inherited read DACL semantics"):
        collision_assets._normalize_staging_permissions(staging)


@pytest.mark.skipif(os.name != "nt", reason="Windows effective DACL behavior")
def test_inherited_deny_before_allow_that_blocks_ordinary_read_is_rejected(
    tmp_path, monkeypatch
):
    """Matching ACE aggregates cannot substitute for ordered effective access."""
    parent, staging, children, icacls = _make_windows_acl_fixture(tmp_path, 1)
    monkeypatch.setattr(collision_assets, "COLLISION_DIR", parent / "collision")
    subprocess.run(
        [
            str(icacls),
            str(parent),
            "/deny",
            "*S-1-1-0:(OI)(IO)(RD)",
            "/Q",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    try:
        subprocess.run(
            [str(icacls), str(staging), "/reset", "/T", "/Q"],
            check=True,
            capture_output=True,
            text=True,
        )
        with pytest.raises(PermissionError):
            children[0].read_bytes()

        with pytest.raises(PermissionError, match="effective read"):
            collision_assets._validate_windows_inherited_dacls(
                parent, (staging, *children)
            )
    finally:
        subprocess.run(
            [str(icacls), str(parent), "/remove:d", "*S-1-1-0", "/Q"],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            [str(icacls), str(staging), "/reset", "/T", "/Q"],
            check=True,
            capture_output=True,
            text=True,
        )


@pytest.mark.skipif(os.name != "nt", reason="Windows parent-relative DACL behavior")
def test_missing_parent_read_semantics_on_staging_root_is_rejected_before_promotion(
    tmp_path, monkeypatch
):
    """SYSTEM-only inheritance must not stand in for both known parent read principals."""
    project_root = tmp_path / "project"
    collision_dir = project_root / "assets" / "collision"
    collision_dir.mkdir(parents=True)
    existing = collision_dir / "d_guide_male_seg_000.stl"
    existing.write_bytes(b"known-good")
    trusted_icacls = shutil.which("icacls.exe")
    assert trusted_icacls is not None
    subprocess.run(
        [
            trusted_icacls,
            str(collision_dir.parent),
            "/grant",
            "*S-1-1-0:(OI)(CI)R",
            "*S-1-5-11:(OI)(CI)R",
            "*S-1-5-18:(OI)(CI)R",
            "/Q",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    monkeypatch.setattr(collision_assets, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(collision_assets, "COLLISION_DIR", collision_dir)
    monkeypatch.setattr(collision_assets, "_generate_into", _write_acl_probe_children)
    monkeypatch.setattr(collision_assets, "_validate_staging_inventory", lambda _directory: ())
    real_run = subprocess.run

    def report_success_but_leave_only_system_read(args, **kwargs):
        completed = real_run(args, **kwargs)
        _forge_unprotected_system_read_dacl(Path(args[1]))
        return completed

    monkeypatch.setattr(collision_assets.subprocess, "run", report_success_but_leave_only_system_read)

    with pytest.raises(PermissionError, match="parent-inherited read DACL semantics"):
        collision_assets.generate_collision_assets()

    assert existing.read_bytes() == b"known-good"
    assert not list(collision_dir.parent.glob(".collision-backup-*"))


@pytest.mark.skipif(os.name != "nt", reason="Windows parent-relative DACL behavior")
def test_inherited_read_deny_on_last_of_696_children_is_rejected_before_promotion(
    tmp_path, monkeypatch
):
    """Checking only the root or a representative child would miss a late broad DENY."""
    project_root = tmp_path / "project"
    collision_dir = project_root / "assets" / "collision"
    collision_dir.mkdir(parents=True)
    existing = collision_dir / "d_guide_male_seg_000.stl"
    existing.write_bytes(b"known-good")
    trusted_icacls = shutil.which("icacls.exe")
    assert trusted_icacls is not None
    subprocess.run(
        [
            trusted_icacls,
            str(collision_dir.parent),
            "/grant",
            "*S-1-1-0:(OI)(CI)R",
            "*S-1-5-11:(OI)(CI)R",
            "*S-1-5-18:(OI)(CI)R",
            "/Q",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    monkeypatch.setattr(collision_assets, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(collision_assets, "COLLISION_DIR", collision_dir)
    monkeypatch.setattr(collision_assets, "_generate_into", _write_acl_probe_children)
    monkeypatch.setattr(collision_assets, "_validate_staging_inventory", lambda _directory: ())
    real_run = subprocess.run

    def report_success_but_add_late_read_deny(args, **kwargs):
        completed = real_run(args, **kwargs)
        _add_inherited_everyone_read_deny(Path(args[1]) / "dummy_695.stl")
        return completed

    monkeypatch.setattr(collision_assets.subprocess, "run", report_success_but_add_late_read_deny)

    with pytest.raises(PermissionError, match="parent-inherited read DACL semantics"):
        collision_assets.generate_collision_assets()

    assert existing.read_bytes() == b"known-good"
    assert not list(collision_dir.parent.glob(".collision-backup-*"))


@pytest.mark.skipif(os.name != "nt", reason="Windows system-directory lookup behavior")
def test_spoofed_systemroot_cannot_redirect_icacls_selection(tmp_path, monkeypatch):
    parent, staging, children, trusted_icacls = _make_windows_acl_fixture(tmp_path, 1)
    fake_system_root = tmp_path / "fake-windows"
    fake_icacls = fake_system_root / "System32" / "icacls.exe"
    fake_icacls.parent.mkdir(parents=True)
    shutil.copy2(trusted_icacls, fake_icacls)
    monkeypatch.setenv("SystemRoot", str(fake_system_root))
    monkeypatch.setattr(collision_assets, "COLLISION_DIR", parent / "collision")
    real_run = subprocess.run
    invoked_executables: list[Path] = []

    def record_executable(args, **kwargs):
        invoked_executables.append(Path(args[0]).resolve())
        return real_run(args, **kwargs)

    monkeypatch.setattr(collision_assets.subprocess, "run", record_executable)

    collision_assets._normalize_staging_permissions(staging)

    assert invoked_executables == [trusted_icacls.resolve()]
    assert not _windows_acl_summary(staging)[0]
    assert not _windows_acl_summary(children[0])[0]


@pytest.mark.skipif(os.name != "nt", reason="Windows DACL postcondition behavior")
def test_success_exit_without_acl_normalization_is_rejected_before_promotion(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    collision_dir = project_root / "assets" / "collision"
    collision_dir.mkdir(parents=True)
    existing = collision_dir / "d_guide_male_seg_000.stl"
    existing.write_bytes(b"known-good")
    monkeypatch.setattr(collision_assets, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(collision_assets, "COLLISION_DIR", collision_dir)
    real_run = subprocess.run
    icacls_text = shutil.which("icacls.exe")
    assert icacls_text is not None

    def write_protected_staging(output_dir):
        (output_dir / "new.stl").write_bytes(b"staged")
        real_run(
            [icacls_text, str(output_dir), "/inheritance:d", "/T", "/Q"],
            check=True,
            capture_output=True,
            text=True,
        )
        return ()

    def report_success_without_changing_acl(*args, **kwargs):
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(collision_assets, "_generate_into", write_protected_staging)
    monkeypatch.setattr(collision_assets, "_validate_staging_inventory", lambda _directory: ())
    monkeypatch.setattr(collision_assets.subprocess, "run", report_success_without_changing_acl)

    with pytest.raises(PermissionError, match="DACL"):
        collision_assets.generate_collision_assets()

    assert existing.read_bytes() == b"known-good"
    assert not list(collision_dir.parent.glob(".collision-backup-*"))


def test_permission_normalization_failure_leaves_previous_target_untouched(tmp_path, monkeypatch):
    """ACL repair is a pre-promotion gate, not a best-effort post-promotion action."""
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

    def fail_normalization(_staging_dir):
        raise PermissionError("injected permission normalization failure")

    monkeypatch.setattr(collision_assets, "_generate_into", write_staged_marker)
    monkeypatch.setattr(collision_assets, "_validate_staging_inventory", lambda _directory: ())
    monkeypatch.setattr(
        collision_assets, "_normalize_staging_permissions", fail_normalization, raising=False
    )

    with pytest.raises(PermissionError, match="injected permission normalization failure"):
        collision_assets.generate_collision_assets()

    assert existing.read_bytes() == b"known-good"
    assert not list(collision_dir.parent.glob(".collision-backup-*"))
