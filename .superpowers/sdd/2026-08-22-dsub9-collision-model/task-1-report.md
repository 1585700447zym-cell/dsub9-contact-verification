# Task 1 Report: Geometry audit and binary STL utilities

## Implementation

- Added `pyproject.toml` with the requested Python, NumPy, pytest, MuJoCo, and pytest discovery configuration.
- Added immutable `Bounds` and `StlMesh` dataclasses plus binary STL read, write, translation, and bounds support.
- Added the source-geometry audit functions.  STEP bounds are calculated exclusively from `CARTESIAN_POINT` entities directly referenced by `VERTEX_POINT`; directions and placement-only points are excluded.
- Added real-file regression tests for the female STL export frame and both STEP mating frames.  No file under `DSub9_Deliverables_V4/` was modified.

## TDD evidence

### RED: binary STL behavior

Command:

```powershell
& 'D:\KEYANRUJIAN\Scripts\pytest.exe' tests/mesh/test_stl_binary.py -v
```

Before the implementation, collection failed as expected with `ModuleNotFoundError: No module named 'tools'` from `tools.mesh.stl_binary`.

### GREEN: binary STL behavior

The same command then reported `2 passed in 0.11s`.

### RED: source-audit behavior

Command:

```powershell
& 'D:\KEYANRUJIAN\Scripts\pytest.exe' tests/mesh/test_source_geometry.py -v
```

With `tools/mesh/audit_geometry.py` intentionally absent, collection failed as expected with `ModuleNotFoundError: No module named 'tools.mesh.audit_geometry'`.

### GREEN: source-audit behavior

After the minimal audit implementation, the full Task 1 suite reported `4 passed in 0.11s`.

## Test commands and results

```powershell
& 'D:\KEYANRUJIAN\Scripts\pytest.exe' tests/mesh/test_stl_binary.py tests/mesh/test_source_geometry.py -v
```

Result: `4 passed in 0.11s`.

```powershell
$projectPython = 'C:\Users\ok everything\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $projectPython -m pytest tests/mesh/test_stl_binary.py tests/mesh/test_source_geometry.py -v
```

Result: cannot run because that required Python does not bundle pytest (`No module named pytest`).  Per the no-network constraint, no package was installed; the existing pytest 8.3.4 environment was used for the passing validation above.

## Changed files

- `pyproject.toml`
- `tools/mesh/__init__.py`
- `tools/mesh/stl_binary.py`
- `tools/mesh/audit_geometry.py`
- `tests/mesh/test_stl_binary.py`
- `tests/mesh/test_source_geometry.py`

## Self-review

- Binary records use the required 80-byte header, little-endian count, 50-byte records, and two attribute bytes.
- The writer validates normal and triangle shapes before writing.
- Translation preserves normals and shifts vertices by exactly the supplied three-coordinate offset.
- STEP parsing stores Cartesian entities first, then selects only IDs referenced in `VERTEX_POINT` entities.
- `git diff --check` was clean and `git diff -- DSub9_Deliverables_V4` was empty.

## Issues

- The prescribed bundled Python cannot execute pytest because pytest is absent.  This is an environment dependency gap only; the Task 1 suite passes using the available local pytest environment.  No network or dependency installation was performed.
