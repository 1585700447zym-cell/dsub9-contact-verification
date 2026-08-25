"""Bounds extraction for binary STL and STEP source models."""

from __future__ import annotations

from pathlib import Path
import re

import numpy as np

from tools.mesh.stl_binary import Bounds, read_binary_stl


_ENTITY = re.compile(r"#(\d+)\s*=\s*([A-Z_]+)\s*\((.*?)\)\s*;", re.DOTALL)
_NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][-+]?\d+)?"
_POINT = re.compile(
    rf"CARTESIAN_POINT\s*\(.*?\(\s*({_NUMBER})\s*,\s*({_NUMBER})\s*,\s*({_NUMBER})\s*\)",
    re.DOTALL,
)
_REFERENCE = re.compile(r"#(\d+)")


def stl_bounds(path: Path) -> Bounds:
    """Return the axis-aligned bounds of a binary STL source file."""
    return read_binary_stl(path).bounds


def step_vertex_bounds(path: Path) -> Bounds:
    """Return bounds of CARTESIAN_POINT entities used by VERTEX_POINT only."""
    text = path.read_text(encoding="utf-8", errors="replace")
    points: dict[str, np.ndarray] = {}
    vertex_point_ids: set[str] = set()

    for entity_id, entity_type, body in _ENTITY.findall(text):
        if entity_type == "CARTESIAN_POINT":
            match = _POINT.search(f"CARTESIAN_POINT({body})")
            if match:
                points[entity_id] = np.array(
                    [float(value.replace("D", "E").replace("d", "e")) for value in match.groups()]
                )
        elif entity_type == "VERTEX_POINT":
            vertex_point_ids.update(_REFERENCE.findall(body))

    vertices = [points[point_id] for point_id in vertex_point_ids if point_id in points]
    if not vertices:
        raise ValueError("STEP file contains no CARTESIAN_POINT referenced by VERTEX_POINT")
    coordinates = np.asarray(vertices)
    return Bounds(coordinates.min(axis=0), coordinates.max(axis=0))
