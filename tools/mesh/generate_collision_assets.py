"""Generate CAD-derived D-guide walls and the polygon32 hole fallback."""

from __future__ import annotations

from collections import Counter
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

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
MALE_D_WALL_PART_COUNT = 78
FEMALE_D_WALL_PART_COUNT = 42
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
    output_dir: Path | None = None,
) -> tuple[list[Path], tuple[np.ndarray, np.ndarray]]:
    destination = COLLISION_DIR if output_dir is None else output_dir
    loops = section_loops(read_binary_stl(mesh_path), section_z_mm, SECTION_TOLERANCE_MM)
    outer, inner = select_centered_d_loops(loops)
    profiles = build_d_wall_profiles(outer, inner, SECTION_TOLERANCE_MM)
    paths: list[Path] = []
    for index, profile in enumerate(profiles):
        target = destination / f"{prefix}_seg_{index:03d}.stl"
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


def _write_fallback_holes(output_dir: Path | None = None) -> list[Path]:
    destination = COLLISION_DIR if output_dir is None else output_dir
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
                target = destination / (
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


def generated_collision_paths(directory: Path | None = None) -> tuple[Path, ...]:
    """Enumerate only the collision assets owned by this generator."""
    destination = COLLISION_DIR if directory is None else directory
    patterns = ("d_guide_male_*.stl", "d_socket_female_*.stl", "hole_fallback_32_*.stl")
    return tuple(sorted(path for pattern in patterns for path in destination.glob(pattern)))


def _expected_collision_names() -> frozenset[str]:
    names = {
        *(f"d_guide_male_seg_{index:03d}.stl" for index in range(MALE_D_WALL_PART_COUNT)),
        *(f"d_socket_female_seg_{index:03d}.stl" for index in range(FEMALE_D_WALL_PART_COUNT)),
    }
    names.update(
        f"hole_fallback_32_h{hole_index:02d}_{layer}_s{sector_index:02d}.stl"
        for hole_index in range(1, len(FALLBACK_HOLE_CENTRES_MM) + 1)
        for layer in ("entry", "main")
        for sector_index in range(SECTOR_COUNT)
    )
    return frozenset(names)


def _validate_staging_inventory(directory: Path) -> tuple[Path, ...]:
    actual = {path.name for path in directory.iterdir()}
    expected = _expected_collision_names()
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        raise ValueError(
            "collision asset inventory mismatch: "
            f"expected={len(expected)}, actual={len(actual)}, "
            f"missing={missing[:3]}, unexpected={unexpected[:3]}"
        )
    paths = tuple(directory / name for name in sorted(expected))
    for path in paths:
        try:
            _validate_collision_mesh(read_binary_stl(path))
        except (OSError, ValueError) as error:
            raise ValueError(f"invalid collision asset {path.name}: {error}") from error
    return paths


def _validate_collision_mesh(mesh: StlMesh) -> None:
    triangles = np.asarray(mesh.triangles, dtype=np.float64)
    normals = np.asarray(mesh.normals, dtype=np.float64)
    if len(triangles) < 12 or not np.isfinite(triangles).all() or not np.isfinite(normals).all():
        raise ValueError("mesh must contain at least 12 finite triangles and normals")
    if np.any(mesh.bounds.size <= 0):
        raise ValueError("mesh bounds must have positive extent on every axis")

    cross_products = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    lengths = np.linalg.norm(cross_products, axis=1)
    if np.any(lengths <= 1e-12):
        raise ValueError("mesh contains a degenerate triangle")
    expected_normals = cross_products / lengths[:, np.newaxis]
    if not np.allclose(normals, expected_normals, atol=2e-6, rtol=0.0):
        raise ValueError("stored facet normals do not match triangle winding")

    edge_counts: Counter[tuple[tuple[float, ...], tuple[float, ...]]] = Counter()
    for triangle in triangles:
        for start, end in zip(triangle, np.roll(triangle, -1, axis=0), strict=True):
            first = tuple(float(value) for value in np.round(start, decimals=5))
            second = tuple(float(value) for value in np.round(end, decimals=5))
            edge_counts[tuple(sorted((first, second)))] += 1
    if not edge_counts or set(edge_counts.values()) != {2}:
        raise ValueError("mesh is not a closed two-manifold")

    signed_volume = np.einsum(
        "ij,ij->i", triangles[:, 0], np.cross(triangles[:, 1], triangles[:, 2])
    ).sum() / 6.0
    if signed_volume <= 1e-8:
        raise ValueError("mesh must have positive signed volume and outward winding")

    vertices = np.unique(triangles.reshape(-1, 3), axis=0)
    centre = vertices.mean(axis=0)
    for triangle, normal in zip(triangles, cross_products, strict=True):
        outward = -normal if np.dot(normal, centre - triangle[0]) > 0 else normal
        if np.max((vertices - triangle[0]) @ outward) > 2e-5 * np.linalg.norm(outward):
            raise ValueError("mesh is not convex")


def _generate_into(output_dir: Path) -> tuple[Path, ...]:
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_d_wall("d_guide_male", MALE_VISUAL, MALE_SECTION_Z_MM, MALE_WALL_Z_MM, output_dir)
    _write_d_wall(
        "d_socket_female", FEMALE_VISUAL, FEMALE_SECTION_Z_MM, FEMALE_WALL_Z_MM, output_dir
    )
    _write_fallback_holes(output_dir)
    return generated_collision_paths(output_dir)


def _unused_sibling_path(parent: Path, prefix: str) -> Path:
    reserved = Path(tempfile.mkdtemp(prefix=prefix, dir=parent))
    reserved.rmdir()
    return reserved


def _assert_safe_target() -> None:
    project_root = PROJECT_ROOT.resolve()
    target = COLLISION_DIR.resolve()
    try:
        target.relative_to(project_root)
    except ValueError as error:
        raise ValueError(f"collision target is outside project workspace: {target}") from error
    expected = (project_root / "assets" / "collision").resolve()
    if target != expected:
        raise ValueError(f"collision target must be the project assets/collision directory: {target}")
    if target.exists() and not target.is_dir():
        raise ValueError(f"collision target is not a directory: {target}")
    if target.exists():
        expected_names = _expected_collision_names()
        unowned = sorted(
            path.name for path in target.iterdir() if not path.is_file() or path.name not in expected_names
        )
        if unowned:
            raise ValueError(
                "collision target contains files not owned by this generator: "
                f"{unowned[:3]}"
            )


def _remove_temporary_directory(path: Path, prefix: str) -> None:
    resolved = path.resolve()
    expected_parent = COLLISION_DIR.parent.resolve()
    if resolved.parent != expected_parent or not resolved.name.startswith(prefix):
        raise ValueError(f"refusing to remove unsafe temporary directory: {resolved}")
    if resolved.exists():
        shutil.rmtree(resolved)


def _trusted_windows_system_directory() -> Path:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_system_directory = kernel32.GetSystemDirectoryW
    get_system_directory.argtypes = [wintypes.LPWSTR, wintypes.UINT]
    get_system_directory.restype = wintypes.UINT
    system_directory_buffer = ctypes.create_unicode_buffer(32768)
    length = get_system_directory(system_directory_buffer, len(system_directory_buffer))
    if length == 0:
        raise ctypes.WinError(ctypes.get_last_error())
    if length >= len(system_directory_buffer):
        raise RuntimeError("Windows system directory exceeds the supported path length")
    return Path(system_directory_buffer.value)


def _normalize_staging_permissions(staging_dir: Path) -> None:
    """Reset a Windows staging tree to the exact assets parent's inherited DACL."""
    if os.name != "nt":
        return
    resolved = staging_dir.resolve()
    expected_parent = COLLISION_DIR.parent.resolve()
    if resolved.parent != expected_parent or not resolved.name.startswith(".collision-staging-"):
        raise ValueError(f"refusing to normalize unsafe staging directory: {resolved}")
    system_directory = _trusted_windows_system_directory()
    icacls = system_directory / "icacls.exe"
    if not icacls.is_file():
        raise FileNotFoundError(f"Windows ACL utility is unavailable: {icacls}")
    subprocess.run(
        [str(icacls), str(resolved), "/reset", "/T", "/Q"],
        check=True,
        capture_output=True,
        text=True,
    )
    _validate_windows_inherited_dacls(
        expected_parent,
        (resolved, *sorted(resolved.rglob("*"))),
        system_directory,
    )


class _AclSizeInformation(ctypes.Structure):
    _fields_ = [
        ("ace_count", wintypes.DWORD),
        ("acl_bytes_in_use", wintypes.DWORD),
        ("acl_bytes_free", wintypes.DWORD),
    ]


class _AceHeader(ctypes.Structure):
    _fields_ = [
        ("ace_type", ctypes.c_ubyte),
        ("ace_flags", ctypes.c_ubyte),
        ("ace_size", wintypes.WORD),
    ]


class _AccessAce(ctypes.Structure):
    _fields_ = [
        ("header", _AceHeader),
        ("mask", wintypes.DWORD),
        ("sid_start", wintypes.DWORD),
    ]


class _GenericMapping(ctypes.Structure):
    _fields_ = [
        ("generic_read", wintypes.DWORD),
        ("generic_write", wintypes.DWORD),
        ("generic_execute", wintypes.DWORD),
        ("generic_all", wintypes.DWORD),
    ]


class _Luid(ctypes.Structure):
    _fields_ = [
        ("low_part", wintypes.DWORD),
        ("high_part", wintypes.LONG),
    ]


class _SidAndAttributes(ctypes.Structure):
    _fields_ = [
        ("sid", ctypes.c_void_p),
        ("attributes", wintypes.DWORD),
    ]


class _AuthzAccessRequest(ctypes.Structure):
    _fields_ = [
        ("desired_access", wintypes.DWORD),
        ("principal_self_sid", ctypes.c_void_p),
        ("object_type_list", ctypes.c_void_p),
        ("object_type_list_length", wintypes.DWORD),
        ("optional_arguments", ctypes.c_void_p),
    ]


class _AuthzAccessReply(ctypes.Structure):
    _fields_ = [
        ("result_list_length", wintypes.DWORD),
        ("granted_access_mask", ctypes.POINTER(wintypes.DWORD)),
        ("sacl_evaluation_results", ctypes.POINTER(wintypes.DWORD)),
        ("error", ctypes.POINTER(wintypes.DWORD)),
    ]


_INHERIT_ONLY_ACE = 0x08
_ACCESS_ALLOWED_ACE_TYPE = 0x00
_ACCESS_DENIED_ACE_TYPE = 0x01
_SUPPORTED_DACL_ACE_TYPES = frozenset(
    (_ACCESS_ALLOWED_ACE_TYPE, _ACCESS_DENIED_ACE_TYPE)
)
_FILE_GENERIC_READ = 0x00120089
_FILE_GENERIC_WRITE = 0x00120116
_FILE_GENERIC_EXECUTE = 0x001200A0
_FILE_ALL_ACCESS = 0x001F01FF
_FILE_READ_DATA = 0x00000001
_AUTHZ_RM_FLAG_NO_AUDIT = 0x00000001
_AUTHZ_SKIP_TOKEN_GROUPS = 0x00000002
_SE_GROUP_USE_FOR_DENY_ONLY = 0x00000010


def _require_supported_dacl_ace_type(ace_type: int, path: Path) -> None:
    """Fail closed for every DACL ACE whose access semantics are unsupported."""
    if ace_type not in _SUPPORTED_DACL_ACE_TYPES:
        raise PermissionError(f"unsupported DACL ACE type {ace_type} in DACL: {path}")


def _validate_windows_inherited_dacls(
    expected_parent: Path,
    paths: tuple[Path, ...],
    system_directory: Path | None = None,
) -> None:
    if not paths:
        raise PermissionError("no staged paths are available for DACL validation")
    if system_directory is None:
        system_directory = _trusted_windows_system_directory()
    authz_path = system_directory / "authz.dll"
    if not authz_path.is_file():
        raise FileNotFoundError(f"Windows authorization library is unavailable: {authz_path}")

    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    authz = ctypes.WinDLL(str(authz_path), use_last_error=True)
    get_named_security_info = advapi32.GetNamedSecurityInfoW
    get_named_security_info.argtypes = [
        wintypes.LPWSTR,
        ctypes.c_int,
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    get_named_security_info.restype = wintypes.DWORD
    get_descriptor_control = advapi32.GetSecurityDescriptorControl
    get_descriptor_control.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_ushort),
        ctypes.POINTER(wintypes.DWORD),
    ]
    get_descriptor_control.restype = wintypes.BOOL
    get_acl_information = advapi32.GetAclInformation
    get_acl_information.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.c_int,
    ]
    get_acl_information.restype = wintypes.BOOL
    get_ace = advapi32.GetAce
    get_ace.argtypes = [
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    get_ace.restype = wintypes.BOOL
    initialize_acl = advapi32.InitializeAcl
    initialize_acl.argtypes = [
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    initialize_acl.restype = wintypes.BOOL
    set_named_security_info = advapi32.SetNamedSecurityInfoW
    set_named_security_info.argtypes = [
        wintypes.LPWSTR,
        ctypes.c_int,
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    set_named_security_info.restype = wintypes.DWORD
    is_valid_sid = advapi32.IsValidSid
    is_valid_sid.argtypes = [ctypes.c_void_p]
    is_valid_sid.restype = wintypes.BOOL
    get_length_sid = advapi32.GetLengthSid
    get_length_sid.argtypes = [ctypes.c_void_p]
    get_length_sid.restype = wintypes.DWORD
    map_generic_mask = advapi32.MapGenericMask
    map_generic_mask.argtypes = [
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(_GenericMapping),
    ]
    map_generic_mask.restype = None
    initialize_resource_manager = authz.AuthzInitializeResourceManager
    initialize_resource_manager.argtypes = [
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.LPWSTR,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    initialize_resource_manager.restype = wintypes.BOOL
    free_resource_manager = authz.AuthzFreeResourceManager
    free_resource_manager.argtypes = [ctypes.c_void_p]
    free_resource_manager.restype = wintypes.BOOL
    initialize_context_from_sid = authz.AuthzInitializeContextFromSid
    initialize_context_from_sid.argtypes = [
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        _Luid,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    initialize_context_from_sid.restype = wintypes.BOOL
    add_sids_to_context = authz.AuthzAddSidsToContext
    add_sids_to_context.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(_SidAndAttributes),
        wintypes.DWORD,
        ctypes.POINTER(_SidAndAttributes),
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    add_sids_to_context.restype = wintypes.BOOL
    access_check = authz.AuthzAccessCheck
    access_check.argtypes = [
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.POINTER(_AuthzAccessRequest),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_AuthzAccessReply),
        ctypes.c_void_p,
    ]
    access_check.restype = wintypes.BOOL
    free_context = authz.AuthzFreeContext
    free_context.argtypes = [ctypes.c_void_p]
    free_context.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p

    generic_mapping = _GenericMapping(
        _FILE_GENERIC_READ,
        _FILE_GENERIC_WRITE,
        _FILE_GENERIC_EXECUTE,
        _FILE_ALL_ACCESS,
    )

    resource_manager = ctypes.c_void_p()
    if not initialize_resource_manager(
        _AUTHZ_RM_FLAG_NO_AUDIT,
        None,
        None,
        None,
        "collision asset ACL validation",
        ctypes.byref(resource_manager),
    ):
        raise ctypes.WinError(ctypes.get_last_error())

    all_contexts: list[tuple[bytes, ctypes.c_void_p, tuple[object, ...]]] = []

    def read_dacl(
        path: Path,
        contexts: tuple[tuple[bytes, ctypes.c_void_p, tuple[object, ...]], ...] = (),
    ) -> tuple[bool, tuple[tuple[int, int, int, bytes], ...]]:
        owner = ctypes.c_void_p()
        group = ctypes.c_void_p()
        dacl = ctypes.c_void_p()
        descriptor = ctypes.c_void_p()
        result = get_named_security_info(
            str(path),
            1,
            0x00000007,
            ctypes.byref(owner),
            ctypes.byref(group),
            ctypes.byref(dacl),
            None,
            ctypes.byref(descriptor),
        )
        if result != 0:
            raise ctypes.WinError(result)
        try:
            control = ctypes.c_ushort()
            revision = wintypes.DWORD()
            if not get_descriptor_control(descriptor, ctypes.byref(control), ctypes.byref(revision)):
                raise ctypes.WinError(ctypes.get_last_error())
            if not dacl.value:
                raise PermissionError(f"null DACL prevents parent-relative validation: {path}")

            acl_info = _AclSizeInformation()
            if not get_acl_information(dacl, ctypes.byref(acl_info), ctypes.sizeof(acl_info), 2):
                raise ctypes.WinError(ctypes.get_last_error())
            entries: list[tuple[int, int, int, bytes]] = []
            for index in range(acl_info.ace_count):
                ace_pointer = ctypes.c_void_p()
                if not get_ace(dacl, index, ctypes.byref(ace_pointer)):
                    raise ctypes.WinError(ctypes.get_last_error())
                header = ctypes.cast(ace_pointer, ctypes.POINTER(_AceHeader)).contents
                _require_supported_dacl_ace_type(header.ace_type, path)
                if header.ace_size < _AccessAce.sid_start.offset + 8:
                    raise PermissionError(f"malformed access ACE in DACL: {path}")
                access_ace = ctypes.cast(
                    ace_pointer, ctypes.POINTER(_AccessAce)
                ).contents
                mapped_mask = wintypes.DWORD(access_ace.mask)
                map_generic_mask(ctypes.byref(mapped_mask), ctypes.byref(generic_mapping))
                read_mask = mapped_mask.value & _FILE_GENERIC_READ
                sid_address = ace_pointer.value + _AccessAce.sid_start.offset
                sid_pointer = ctypes.c_void_p(sid_address)
                if not is_valid_sid(sid_pointer):
                    raise PermissionError(f"malformed SID in DACL access ACE: {path}")
                sid_length = get_length_sid(sid_pointer)
                if sid_length != header.ace_size - _AccessAce.sid_start.offset:
                    raise PermissionError(f"malformed SID extent in DACL access ACE: {path}")
                if read_mask:
                    entries.append(
                        (
                            header.ace_type,
                            header.ace_flags,
                            read_mask,
                            ctypes.string_at(sid_address, sid_length),
                        )
                    )

            for subject_sid, context, _keepalive in contexts:
                granted = wintypes.DWORD()
                sacl_result = wintypes.DWORD()
                access_error = wintypes.DWORD()
                request = _AuthzAccessRequest(
                    _FILE_GENERIC_READ,
                    None,
                    None,
                    0,
                    None,
                )
                reply = _AuthzAccessReply(
                    1,
                    ctypes.pointer(granted),
                    ctypes.pointer(sacl_result),
                    ctypes.pointer(access_error),
                )
                if not access_check(
                    0,
                    context,
                    ctypes.byref(request),
                    None,
                    descriptor,
                    None,
                    0,
                    ctypes.byref(reply),
                    None,
                ):
                    raise ctypes.WinError(ctypes.get_last_error())
                if (
                    access_error.value != 0
                    or granted.value & _FILE_GENERIC_READ != _FILE_GENERIC_READ
                ):
                    raise PermissionError(
                        "parent-inherited read DACL semantics mismatch: "
                        "effective read denied after normalization for "
                        f"SID {subject_sid.hex()} on {path}"
                    )
            return bool(control.value & 0x1000), tuple(entries)
        finally:
            if descriptor.value:
                kernel32.LocalFree(descriptor)

    def build_contexts(
        entries: tuple[tuple[int, int, int, bytes], ...],
        reference_path: Path,
    ) -> tuple[tuple[bytes, ctypes.c_void_p, tuple[object, ...]], ...]:
        subjects: list[bytes] = []
        deny_sids: list[bytes] = []
        for ace_type, ace_flags, read_mask, sid in entries:
            if ace_flags & _INHERIT_ONLY_ACE:
                continue
            if (
                ace_type == _ACCESS_ALLOWED_ACE_TYPE
                and read_mask & _FILE_READ_DATA
                and sid not in subjects
            ):
                subjects.append(sid)
            if ace_type == _ACCESS_DENIED_ACE_TYPE and sid not in deny_sids:
                deny_sids.append(sid)
        if not subjects:
            raise PermissionError(
                f"assets parent produces no applicable read ALLOW subjects: {reference_path}"
            )

        built: list[tuple[bytes, ctypes.c_void_p, tuple[object, ...]]] = []
        try:
            for subject_sid in subjects:
                subject_buffer = ctypes.create_string_buffer(subject_sid)
                base_context = ctypes.c_void_p()
                if not initialize_context_from_sid(
                    _AUTHZ_SKIP_TOKEN_GROUPS,
                    ctypes.cast(subject_buffer, ctypes.c_void_p),
                    resource_manager,
                    None,
                    _Luid(),
                    None,
                    ctypes.byref(base_context),
                ):
                    raise ctypes.WinError(ctypes.get_last_error())

                keepalive: list[object] = [subject_buffer]
                context = base_context
                if deny_sids:
                    deny_buffers = [ctypes.create_string_buffer(sid) for sid in deny_sids]
                    deny_entries = (_SidAndAttributes * len(deny_buffers))(
                        *(
                            _SidAndAttributes(
                                ctypes.cast(buffer, ctypes.c_void_p),
                                _SE_GROUP_USE_FOR_DENY_ONLY,
                            )
                            for buffer in deny_buffers
                        )
                    )
                    expanded_context = ctypes.c_void_p()
                    if not add_sids_to_context(
                        base_context,
                        deny_entries,
                        len(deny_entries),
                        None,
                        0,
                        ctypes.byref(expanded_context),
                    ):
                        error = ctypes.WinError(ctypes.get_last_error())
                        free_context(base_context)
                        raise error
                    free_context(base_context)
                    context = expanded_context
                    keepalive.extend((*deny_buffers, deny_entries))
                built.append((subject_sid, context, tuple(keepalive)))
            return tuple(built)
        except BaseException:
            for _sid, context, _keepalive in built:
                free_context(context)
            raise

    def reset_reference_to_inherited_dacl(path: Path) -> None:
        """Ask the kernel to derive a fresh unprotected DACL from the exact parent."""
        empty_acl = ctypes.create_string_buffer(8)
        if not initialize_acl(empty_acl, len(empty_acl), 2):
            raise ctypes.WinError(ctypes.get_last_error())
        result = set_named_security_info(
            str(path),
            1,
            0x20000004,
            None,
            None,
            empty_acl,
            None,
        )
        if result != 0:
            raise ctypes.WinError(result)

    probe_dir: Path | None = None
    try:
        probe_dir = Path(
            tempfile.mkdtemp(prefix=".collision-acl-probe-", dir=expected_parent)
        ).resolve()
        reset_reference_to_inherited_dacl(probe_dir)
        probe_file = probe_dir / "probe.stl"
        probe_file.write_bytes(b"acl-probe")
        reset_reference_to_inherited_dacl(probe_file)
        root_protected, root_reference = read_dacl(probe_dir)
        file_protected, file_reference = read_dacl(probe_file)
        if root_protected or file_protected:
            raise PermissionError(
                f"assets parent produces protected inherited DACLs: {expected_parent}"
            )

        root_contexts = build_contexts(root_reference, probe_dir)
        all_contexts.extend(root_contexts)
        file_contexts = build_contexts(file_reference, probe_file)
        all_contexts.extend(file_contexts)
        read_dacl(probe_dir, root_contexts)
        read_dacl(probe_file, file_contexts)

        def validate_path(
            path: Path,
            reference: tuple[tuple[int, int, int, bytes], ...],
            contexts: tuple[tuple[bytes, ctypes.c_void_p, tuple[object, ...]], ...],
        ) -> None:
            protected, entries = read_dacl(path, contexts)
            if protected:
                raise PermissionError(f"protected DACL remains after normalization: {path}")
            if entries != reference:
                raise PermissionError(
                    f"parent-inherited read DACL semantics mismatch after normalization: {path}"
                )

        validate_path(paths[0], root_reference, root_contexts)
        for path in paths[1:]:
            validate_path(path, file_reference, file_contexts)
    finally:
        for _sid, context, _keepalive in all_contexts:
            free_context(context)
        if resource_manager.value:
            free_resource_manager(resource_manager)
        if probe_dir is not None:
            _remove_temporary_directory(probe_dir, ".collision-acl-probe-")


def _promote_staging_directory(staging_dir: Path, target_dir: Path) -> None:
    backup_dir: Path | None = None
    try:
        if target_dir.exists():
            backup_dir = _unused_sibling_path(target_dir.parent, ".collision-backup-")
            target_dir.replace(backup_dir)
        staging_dir.replace(target_dir)
    except BaseException:
        if backup_dir is not None and backup_dir.exists():
            rollback_error: BaseException | None = None
            try:
                if target_dir.exists():
                    if staging_dir.exists():
                        raise OSError(
                            "cannot roll back while both target and staging directories exist"
                        )
                    target_dir.replace(staging_dir)
                backup_dir.replace(target_dir)
            except BaseException as error:
                rollback_error = error
            if not target_dir.exists() or backup_dir.exists():
                raise RuntimeError(
                    f"collision replacement and rollback failed; previous assets remain at {backup_dir}"
                ) from rollback_error
        raise
    if backup_dir is not None:
        _remove_temporary_directory(backup_dir, ".collision-backup-")


def generate_collision_assets() -> tuple[Path, ...]:
    """Regenerate all Task 3 collision assets deterministically."""
    _assert_safe_target()
    COLLISION_DIR.parent.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(tempfile.mkdtemp(prefix=".collision-staging-", dir=COLLISION_DIR.parent))
    try:
        _generate_into(staging_dir)
        _validate_staging_inventory(staging_dir)
        _normalize_staging_permissions(staging_dir)
        _promote_staging_directory(staging_dir, COLLISION_DIR)
        paths = generated_collision_paths()
    except BaseException as primary_error:
        try:
            _remove_temporary_directory(staging_dir, ".collision-staging-")
        except BaseException as cleanup_error:
            raise RuntimeError(
                f"{primary_error}; staging cleanup also failed: {cleanup_error}"
            ) from primary_error
        raise
    _remove_temporary_directory(staging_dir, ".collision-staging-")
    print(f"generated {len(paths)} collision STL parts in {COLLISION_DIR}")
    return paths


def main() -> None:
    generate_collision_assets()


if __name__ == "__main__":
    main()
