from __future__ import annotations

import numpy as np

from tools.mesh.stl_binary import StlMesh, read_binary_stl, translated, write_binary_stl


def mesh_fixture() -> StlMesh:
    return StlMesh(
        normals=np.array([[0.0, 0.0, 1.0]], dtype=np.float32),
        triangles=np.array(
            [[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]],
            dtype=np.float32,
        ),
    )


def test_binary_stl_round_trip_preserves_bounds(tmp_path):
    """A parser that reads records at the wrong offsets changes geometry."""
    target = tmp_path / "one_triangle.stl"
    write_binary_stl(target, mesh_fixture())
    loaded = read_binary_stl(target)
    np.testing.assert_allclose(loaded.bounds.minimum, [0.0, 0.0, 0.0])
    np.testing.assert_allclose(loaded.bounds.maximum, [1.0, 1.0, 0.0])


def test_translation_changes_position_not_size():
    """A translation must not accidentally rescale the mesh."""
    source = mesh_fixture()
    moved = translated(source, np.array([-15.4, -6.275, 0.0]))
    np.testing.assert_allclose(moved.bounds.size, source.bounds.size)
    np.testing.assert_allclose(
        moved.bounds.minimum,
        source.bounds.minimum + [-15.4, -6.275, 0.0],
    )
