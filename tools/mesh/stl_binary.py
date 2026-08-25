"""Minimal binary STL reader, writer, and coordinate utilities."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct

import numpy as np


@dataclass(frozen=True)
class Bounds:
    """Axis-aligned bounds in millimetres."""

    minimum: np.ndarray
    maximum: np.ndarray

    @property
    def size(self) -> np.ndarray:
        return self.maximum - self.minimum


@dataclass(frozen=True)
class StlMesh:
    """Triangle normals and vertices from a binary STL file."""

    normals: np.ndarray
    triangles: np.ndarray

    @property
    def bounds(self) -> Bounds:
        vertices = self.triangles.reshape(-1, 3)
        return Bounds(vertices.min(axis=0), vertices.max(axis=0))


def read_binary_stl(path: Path) -> StlMesh:
    """Read a binary STL's normals and triangle vertices."""
    with path.open("rb") as stream:
        header = stream.read(80)
        if len(header) != 80:
            raise ValueError("binary STL header is shorter than 80 bytes")
        count_bytes = stream.read(4)
        if len(count_bytes) != 4:
            raise ValueError("binary STL is missing its triangle count")
        triangle_count = struct.unpack("<I", count_bytes)[0]
        records = stream.read()

    expected_size = triangle_count * 50
    if len(records) != expected_size:
        raise ValueError("binary STL record data does not match its triangle count")

    values = np.empty((triangle_count, 12), dtype=np.float32)
    for index in range(triangle_count):
        record = records[index * 50 : (index + 1) * 50]
        values[index] = struct.unpack("<12f", record[:48])
    return StlMesh(normals=values[:, :3], triangles=values[:, 3:].reshape(-1, 3, 3))


def write_binary_stl(path: Path, mesh: StlMesh) -> None:
    """Write a binary STL with zeroed 80-byte header and attribute bytes."""
    normals = np.asarray(mesh.normals, dtype=np.float32)
    triangles = np.asarray(mesh.triangles, dtype=np.float32)
    if normals.ndim != 2 or normals.shape[1:] != (3,):
        raise ValueError("normals must have shape (triangle_count, 3)")
    if triangles.ndim != 3 or triangles.shape[1:] != (3, 3):
        raise ValueError("triangles must have shape (triangle_count, 3, 3)")
    if len(normals) != len(triangles):
        raise ValueError("normals and triangles must have the same triangle count")

    with path.open("wb") as stream:
        stream.write(b"\0" * 80)
        stream.write(struct.pack("<I", len(triangles)))
        for normal, triangle in zip(normals, triangles, strict=True):
            stream.write(struct.pack("<12fH", *normal, *triangle.reshape(-1), 0))


def translated(mesh: StlMesh, offset_mm: np.ndarray) -> StlMesh:
    """Return a mesh shifted by the supplied millimetre offset."""
    offset = np.asarray(offset_mm, dtype=np.float32)
    if offset.shape != (3,):
        raise ValueError("offset_mm must contain exactly three coordinates")
    return StlMesh(normals=mesh.normals.copy(), triangles=mesh.triangles + offset)
