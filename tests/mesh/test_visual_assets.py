from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from tools.mesh.audit_geometry import stl_bounds
from tools.mesh.stl_binary import StlMesh, read_binary_stl, write_binary_stl
import tools.mesh.normalize_visual_meshes as visual_meshes


VISUAL = Path(__file__).parents[2] / "assets" / "visual"
SOURCE = Path(__file__).parents[2] / "DSub9_Deliverables_V4" / "DSub9_Female_Refined_V3.STL"


def test_centered_female_visual_bounds():
    """Dropping the assembly-frame translation would break the mating frame."""
    bounds = stl_bounds(VISUAL / "dsub9_female_visual_centered.stl")
    np.testing.assert_allclose(bounds.minimum, [-15.4, -6.275, 0.0], atol=2e-5)
    np.testing.assert_allclose(bounds.maximum, [15.4, 6.275, 9.7], atol=2e-5)


def test_centered_male_visual_bounds():
    """A millimetre-scale or origin error would make the mating frame unusable."""
    bounds = stl_bounds(VISUAL / "dsub9_male_visual_centered.stl")
    np.testing.assert_allclose(bounds.minimum, [-15.4, -7.0, -22.0], atol=0.02)
    np.testing.assert_allclose(bounds.maximum, [15.4, 7.0, 4.0], atol=0.02)


def test_normalize_female_translates_triangles_and_recomputes_normals(tmp_path: Path):
    """A stale normal or an incorrect mating-frame shift must not be written."""
    target = tmp_path / "female_centered.stl"
    source_mesh = read_binary_stl(SOURCE)

    visual_meshes.normalize_female(SOURCE, target)

    result = read_binary_stl(target)
    expected_triangles = source_mesh.triangles + np.asarray([-15.4, -6.275, 0.0], dtype=np.float32)
    expected_normals = np.cross(
        expected_triangles[:, 1] - expected_triangles[:, 0],
        expected_triangles[:, 2] - expected_triangles[:, 0],
    )
    expected_normals /= np.linalg.norm(expected_normals, axis=1)[:, np.newaxis]
    np.testing.assert_array_equal(result.triangles, expected_triangles)
    np.testing.assert_allclose(result.normals, expected_normals, rtol=0.0, atol=1e-7)


def _write_mesh_with_bounds(path: Path, minimum: list[float], maximum: list[float]) -> None:
    """Write two non-degenerate triangles whose combined bounds are exact."""
    low = np.asarray(minimum, dtype=np.float32)
    high = np.asarray(maximum, dtype=np.float32)
    triangles = np.asarray(
        [
            [low, [high[0], low[1], low[2]], [low[0], high[1], low[2]]],
            [high, [low[0], high[1], high[2]], [high[0], low[1], high[2]]],
        ],
        dtype=np.float32,
    )
    write_binary_stl(path, StlMesh(normals=np.zeros((2, 3), dtype=np.float32), triangles=triangles))


def test_normalize_female_rejects_source_size_over_tolerance(tmp_path: Path):
    """Changing the source dimensions by more than 0.001 mm must stop conversion."""
    source = tmp_path / "oversized_source.stl"
    _write_mesh_with_bounds(source, [0.0, 0.0, 0.0], [30.802, 12.55, 9.7])

    with pytest.raises(ValueError, match="female source STL dimensions"):
        visual_meshes.normalize_female(source, tmp_path / "ignored.stl")


def test_normalize_female_rejects_degenerate_triangles(tmp_path: Path):
    """A zero-area face must not receive a fabricated normal during conversion."""
    source = tmp_path / "degenerate_source.stl"
    triangles = np.asarray(
        [
            [[0.0, 0.0, 0.0], [30.8, 0.0, 0.0], [0.0, 12.55, 9.7]],
            [[1.0, 1.0, 1.0], [1.0, 1.0, 1.0], [1.0, 1.0, 1.0]],
        ],
        dtype=np.float32,
    )
    write_binary_stl(source, StlMesh(normals=np.zeros((2, 3), dtype=np.float32), triangles=triangles))

    with pytest.raises(ValueError, match="degenerate triangle"):
        visual_meshes.normalize_female(source, tmp_path / "ignored.stl")


def test_validate_male_export_rejects_thousand_fold_scale(tmp_path: Path):
    candidate = tmp_path / "scaled_male.stl"
    _write_mesh_with_bounds(candidate, [-15400.0, -7000.0, -22000.0], [15400.0, 7000.0, 4000.0])

    with pytest.raises(ValueError, match="mating-frame bounds"):
        visual_meshes.validate_male_export(candidate)


def test_validate_male_export_rejects_wrong_origin(tmp_path: Path):
    candidate = tmp_path / "wrong_origin_male.stl"
    _write_mesh_with_bounds(candidate, [0.0, 0.0, 0.0], [30.8, 14.0, 26.0])

    with pytest.raises(ValueError, match="mating-frame bounds"):
        visual_meshes.validate_male_export(candidate)
