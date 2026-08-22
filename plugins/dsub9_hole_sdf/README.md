# D-sub9 analytic circular-hole SDF

This MuJoCo 3.x plugin registers `mujoco.sdf.dsub9_hole`. It describes the
exact stepped socket-material profile, not the polygon32 fallback collision
mesh.

## Geometry and sign

All attributes are in metres and must satisfy
`0 < bore_radius < entry_radius < outer_radius` and
`0 < entry_depth < bore_depth`. Non-finite values are rejected. Defaults are:

- `bore_radius=0.000575`
- `entry_radius=0.000675`
- `entry_depth=0.00025`
- `bore_depth=0.00450`
- `outer_radius=0.00100`

Rotational symmetry reduces the solid to a counter-clockwise six-edge polygon
in the `(r,z)` plane:

```
(entry_radius, 0)
(outer_radius, 0)
(outer_radius, bore_depth)
(bore_radius, bore_depth)
(bore_radius, entry_depth)
(entry_radius, entry_depth)
```

The unsigned distance is the minimum Euclidean point-to-segment distance over
the bottom, outer wall, top, main-bore wall, shoulder, and entry wall. An
odd-even polygon test makes that distance negative inside material and
positive in free space, matching MuJoCo's SDF convention. This avoids the
internal false zero plane produced by taking `min` of two finite annulus SDFs
whose coincident end faces are not boundaries of the union. The gradient
comes from the unique nearest segment or endpoint. Exact ties deterministically
select the first segment in the order above in both Python and C++.

## Windows build

The verified SDK layout is the `mujoco` Python package containing
`include/mujoco` and `mujoco.dll`. Configure with an installed MSVC C++
workload:

```powershell
$python = 'D:\KEYANRUJIAN\python.exe'
$mujocoRoot = & $python -c "import pathlib,mujoco; print(pathlib.Path(mujoco.__file__).resolve().parent)"
cmake -S plugins/dsub9_hole_sdf -B build/dsub9_hole_sdf -G "Visual Studio 18 2026" -A x64 -DMUJOCO_ROOT="$mujocoRoot"
cmake --build build/dsub9_hole_sdf --config Release
```

The expected library is `build/dsub9_hole_sdf/Release/dsub9_hole_sdf.dll`.
Load it after importing MuJoCo:

```python
import mujoco
mujoco.mj_loadPluginLibrary(r"build\dsub9_hole_sdf\Release\dsub9_hole_sdf.dll")
```

The Python wheel does not include a `mujoco.lib` import library. The plugin
therefore resolves `mjp_defaultPlugin`, `mjp_registerPlugin`, and
`mj_getPluginConfig` from the already loaded `mujoco.dll`. This is the same
public 3.9.0 plugin ABI used by MuJoCo's bundled plugins and supports standard
`mj_loadPluginLibrary` loading.
