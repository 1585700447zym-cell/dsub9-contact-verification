# D-sub9 analytic circular-hole SDF

This MuJoCo 3.x plugin registers `mujoco.sdf.dsub9_hole`. It describes socket
material as the continuous union of two finite annuli, not as the polygon32
fallback collision mesh.

## Geometry and sign

All attributes are in metres and must satisfy
`0 < bore_radius < entry_radius < outer_radius` and
`0 < entry_depth < bore_depth`. Non-finite values are rejected. Defaults are:

- `bore_radius=0.000575`
- `entry_radius=0.000675`
- `entry_depth=0.00025`
- `bore_depth=0.00450`
- `outer_radius=0.00100`

For an annulus with radial interval `[ri, ro]` and axial interval `[z0, z1]`,
the code evaluates the exact rectangle SDF in the rotationally symmetric
`(r,z)` plane:

```
q = (abs(r - (ri+ro)/2) - (ro-ri)/2,
     abs(z - (z0+z1)/2) - (z1-z0)/2)
d = length(max(q, 0)) + min(max(q.x, q.y), 0)
```

The entrance annulus uses `[entry_radius, outer_radius] x [0, entry_depth]`;
the main annulus uses `[bore_radius, outer_radius] x
[entry_depth, bore_depth]`. Their union is `min(d_entry, d_main)`. Thus free
bore space is positive and solid socket material is negative, matching
MuJoCo's SDF convention. The analytic gradient uses the same branches; CSG
ties are non-differentiable and parity tests deliberately avoid them.

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
