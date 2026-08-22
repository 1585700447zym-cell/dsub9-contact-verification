"""Create and validate visual meshes in the shared D-sub9 mating frame."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from tools.mesh.stl_binary import Bounds, StlMesh, read_binary_stl, write_binary_stl


FEMALE_SOURCE_SIZE_MM = np.array([30.8, 12.55, 9.7], dtype=np.float32)
FEMALE_OFFSET_MM = np.array([-15.4, -6.275, 0.0], dtype=np.float32)
MALE_EXPECTED_MIN_MM = np.array([-15.4, -7.0, -22.0], dtype=np.float32)
MALE_EXPECTED_MAX_MM = np.array([15.4, 7.0, 4.0], dtype=np.float32)
MALE_BOUNDS_ATOL_MM = 0.02
PROJECT_ROOT = Path(__file__).parents[2]
FEMALE_SOURCE = PROJECT_ROOT / "DSub9_Deliverables_V4" / "DSub9_Female_Refined_V3.STL"
FEMALE_TARGET = PROJECT_ROOT / "assets" / "visual" / "dsub9_female_visual_centered.stl"


def recompute_normals(triangles: np.ndarray) -> np.ndarray:
    """Return unit face normals computed from the supplied triangle vertices."""
    edges_a = triangles[:, 1] - triangles[:, 0]
    edges_b = triangles[:, 2] - triangles[:, 0]
    normals = np.cross(edges_a, edges_b)
    lengths = np.linalg.norm(normals, axis=1)
    if np.any(lengths == 0):
        raise ValueError("STL contains a degenerate triangle")
    return normals / lengths[:, np.newaxis]


def normalize_female(source: Path, target: Path) -> Bounds:
    """Centre the known female STL export and recalculate its face normals."""
    source_mesh = read_binary_stl(source)
    if not np.allclose(source_mesh.bounds.size, FEMALE_SOURCE_SIZE_MM, atol=0.001, rtol=0.0):
        raise ValueError(
            "female source STL dimensions must be "
            f"{FEMALE_SOURCE_SIZE_MM.tolist()} mm; got {source_mesh.bounds.size.tolist()} mm"
        )

    triangles = source_mesh.triangles + FEMALE_OFFSET_MM
    centred = StlMesh(normals=recompute_normals(triangles), triangles=triangles)
    target.parent.mkdir(parents=True, exist_ok=True)
    write_binary_stl(target, centred)
    return centred.bounds


def validate_male_export(path: Path) -> Bounds:
    """Reject a male visual STL that is not in the centred mating frame."""
    bounds = read_binary_stl(path).bounds
    if not (
        np.allclose(bounds.minimum, MALE_EXPECTED_MIN_MM, atol=MALE_BOUNDS_ATOL_MM, rtol=0.0)
        and np.allclose(bounds.maximum, MALE_EXPECTED_MAX_MM, atol=MALE_BOUNDS_ATOL_MM, rtol=0.0)
    ):
        raise ValueError(
            "male export must use centred mating-frame bounds "
            f"min={MALE_EXPECTED_MIN_MM.tolist()}, max={MALE_EXPECTED_MAX_MM.tolist()} mm; "
            f"got min={bounds.minimum.tolist()}, max={bounds.maximum.tolist()} mm"
        )
    return bounds


def main() -> None:
    """Run the deterministic female visual-mesh normalisation."""
    parser = argparse.ArgumentParser()
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--female", action="store_true", help="create the centred female visual STL")
    actions.add_argument("--validate-male", type=Path, metavar="PATH", help="validate a male visual STL")
    arguments = parser.parse_args()
    if arguments.female:
        bounds = normalize_female(FEMALE_SOURCE, FEMALE_TARGET)
        print(f"created {FEMALE_TARGET}: min={bounds.minimum.tolist()}, max={bounds.maximum.tolist()}")
    else:
        bounds = validate_male_export(arguments.validate_male)
        print(f"validated {arguments.validate_male}: min={bounds.minimum.tolist()}, max={bounds.maximum.tolist()}")


if __name__ == "__main__":
    main()
