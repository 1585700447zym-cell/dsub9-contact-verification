# D-sub9 Collision Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build centered D-sub9 visual STL assets and a MuJoCo 3.x collision-validation scene containing the D-shaped guides, nine analytic male pins, and nine true circular female holes represented by analytic SDFs.

**Architecture:** Keep source CAD immutable and generate all derived assets through focused tools. Visual meshes are collision-disabled; D-shaped guide surfaces use convex components, male pins use analytic cylinders, and female bores use a custom analytic SDF plugin with a documented 32-sided fallback. Geometry tests run before MuJoCo integration tests, and contact validation must pass before any controller or RL work begins.

**Tech Stack:** PowerShell 7/Windows, bundled Python 3, NumPy, pytest, MuJoCo 3.x Python package and C plugin API, CMake/MSVC, SolidWorks 2023 for the STEP-to-STL export.

**Spec:** `docs/superpowers/specs/2026-08-22-dsub9-collision-model-design.md`

## Global Constraints

- Preserve every file under `DSub9_Deliverables_V4/`; derived files go under `assets/`, `models/`, `plugins/`, `tools/`, `tests/`, and `reports/`.
- CAD/STL dimensions are millimetres; MJCF dimensions are metres and mesh assets use scale `0.001 0.001 0.001`.
- Female task frame: origin at the insertion-face centre; +Z points into the bores.
- Male task frame: origin at the D-guide and pin-array centre; +Z points from pin roots to pin tips.
- Nominal male pin: diameter 1.00 mm, length 4.00 mm. Nominal female bore: diameter 1.15 mm, depth 4.50 mm, with a diameter 1.35 mm by 0.25 mm entrance section.
- Formal collision model retains all nine pin-hole pairs. It must not substitute a convex hull that fills a hole.
- Visual meshes have `contype="0" conaffinity="0"`.
- Absolute real insertion force is outside this plan; no simulated Newton value may be described as calibrated.
- Subagent-driven execution uses a local Git repository, an isolated worktree, and task-scoped commits. Do not create a remote, push, publish, or merge outside the isolated worktree during this plan.

---

### Task 1: Geometry audit and binary STL utilities

**Files:**
- Create: `pyproject.toml`
- Create: `tools/mesh/__init__.py`
- Create: `tools/mesh/stl_binary.py`
- Create: `tools/mesh/audit_geometry.py`
- Create: `tests/mesh/test_stl_binary.py`
- Create: `tests/mesh/test_source_geometry.py`

**Interfaces:**
- Consumes: binary STL files and STEP text exported by SolidWorks.
- Produces: `read_binary_stl(path: Path) -> StlMesh`, `write_binary_stl(path: Path, mesh: StlMesh) -> None`, `translated(mesh: StlMesh, offset_mm: np.ndarray) -> StlMesh`, `stl_bounds(path: Path) -> Bounds`, and `step_vertex_bounds(path: Path) -> Bounds`.

- [ ] **Step 1: Add package and test configuration**

Create `pyproject.toml` with Python `>=3.11`, runtime dependency `numpy>=1.26`, optional test dependencies `pytest>=8` and `mujoco>=3.3,<4`, plus pytest paths set to `tests`.

```toml
[build-system]
requires = ["setuptools>=69"]
build-backend = "setuptools.build_meta"

[project]
name = "dsub9-first-stage-sim"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["numpy>=1.26"]

[project.optional-dependencies]
test = ["pytest>=8", "mujoco>=3.3,<4"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

- [ ] **Step 2: Write failing STL round-trip tests**

```python
def test_binary_stl_round_trip_preserves_bounds(tmp_path):
    mesh = StlMesh(
        normals=np.array([[0.0, 0.0, 1.0]], dtype=np.float32),
        triangles=np.array([[[0, 0, 0], [1, 0, 0], [0, 1, 0]]], dtype=np.float32),
    )
    target = tmp_path / "one_triangle.stl"
    write_binary_stl(target, mesh)
    loaded = read_binary_stl(target)
    np.testing.assert_allclose(loaded.bounds.minimum, [0, 0, 0])
    np.testing.assert_allclose(loaded.bounds.maximum, [1, 1, 0])


def test_translation_changes_position_not_size():
    moved = translated(mesh_fixture(), np.array([-15.4, -6.275, 0.0]))
    np.testing.assert_allclose(moved.bounds.size, mesh_fixture().bounds.size)
    np.testing.assert_allclose(
        moved.bounds.minimum,
        mesh_fixture().bounds.minimum + [-15.4, -6.275, 0.0],
    )
```

- [ ] **Step 3: Run the focused tests and verify failure**

```powershell
$projectPython = 'C:\Users\ok everything\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $projectPython -m pytest tests/mesh/test_stl_binary.py -v
```

Expected: collection or import failure because `tools.mesh.stl_binary` does not exist.

- [ ] **Step 4: Implement the minimal STL and STEP audit functions**

Use a frozen `Bounds` dataclass containing `minimum`, `maximum`, and computed `size`; a mutable-free `StlMesh` dataclass containing normals and triangles; parse the 80-byte header, little-endian triangle count, 50-byte records, and attribute bytes. `step_vertex_bounds` must extract only `CARTESIAN_POINT` entities referenced by `VERTEX_POINT`, excluding directions and placement-only points.

```python
@dataclass(frozen=True)
class Bounds:
    minimum: np.ndarray
    maximum: np.ndarray

    @property
    def size(self) -> np.ndarray:
        return self.maximum - self.minimum


@dataclass(frozen=True)
class StlMesh:
    normals: np.ndarray
    triangles: np.ndarray

    @property
    def bounds(self) -> Bounds:
        vertices = self.triangles.reshape(-1, 3)
        return Bounds(vertices.min(axis=0), vertices.max(axis=0))
```

- [ ] **Step 5: Add source-coordinate regression tests**

```python
def test_female_source_stl_has_known_export_offset():
    bounds = stl_bounds(SOURCE / "DSub9_Female_Refined_V3.STL")
    np.testing.assert_allclose(bounds.minimum, [0.0, 0.0, 0.0], atol=1e-6)
    np.testing.assert_allclose(bounds.maximum, [30.8, 12.55, 9.7], atol=2e-5)


def test_step_sources_use_mating_frames():
    female = step_vertex_bounds(SOURCE / "DSub9_Female_Refined_V3.step")
    male = step_vertex_bounds(SOURCE / "DSub9_Male_TwoStageRearShell_V3.step")
    np.testing.assert_allclose(female.minimum, [-15.4, -6.275, 0.0])
    np.testing.assert_allclose(female.maximum, [15.4, 6.275, 9.7])
    np.testing.assert_allclose(male.minimum, [-15.4, -7.0, -22.0])
    np.testing.assert_allclose(male.maximum, [15.4, 7.0, 4.0])
```

- [ ] **Step 6: Run Task 1 tests**

```powershell
& $projectPython -m pytest tests/mesh/test_stl_binary.py tests/mesh/test_source_geometry.py -v
```

Expected: all Task 1 tests pass and the source models remain unchanged.

---

### Task 2: Centered visual STL assets

**Files:**
- Create: `tools/mesh/normalize_visual_meshes.py`
- Create: `assets/visual/dsub9_female_visual_centered.stl`
- Create: `assets/visual/dsub9_male_visual_centered.stl`
- Create: `tests/mesh/test_visual_assets.py`
- Create: `reports/solidworks_export_settings.md`

**Interfaces:**
- Consumes: Task 1 STL utilities, source female STL, and SolidWorks male STEP.
- Produces: `normalize_female(source: Path, target: Path) -> Bounds`, `validate_male_export(path: Path) -> Bounds`, and two centered visual STL assets.

- [ ] **Step 1: Write failing visual-asset tests**

```python
def test_centered_female_visual_bounds():
    bounds = stl_bounds(VISUAL / "dsub9_female_visual_centered.stl")
    np.testing.assert_allclose(bounds.minimum, [-15.4, -6.275, 0.0], atol=2e-5)
    np.testing.assert_allclose(bounds.maximum, [15.4, 6.275, 9.7], atol=2e-5)


def test_centered_male_visual_bounds():
    bounds = stl_bounds(VISUAL / "dsub9_male_visual_centered.stl")
    np.testing.assert_allclose(bounds.minimum, [-15.4, -7.0, -22.0], atol=0.02)
    np.testing.assert_allclose(bounds.maximum, [15.4, 7.0, 4.0], atol=0.02)
```

- [ ] **Step 2: Verify tests fail because derived assets are absent**

```powershell
& $projectPython -m pytest tests/mesh/test_visual_assets.py -v
```

Expected: both tests fail with missing-file errors.

- [ ] **Step 3: Implement and run deterministic female normalization**

`normalize_female` must read the source binary STL, apply exactly `[-15.4, -6.275, 0.0]` mm, recompute triangle normals from translated vertices, and write the derived binary STL. It must reject any source whose size differs from `[30.8, 12.55, 9.7]` mm by more than `0.001` mm.

```powershell
& $projectPython -m tools.mesh.normalize_visual_meshes --female
```

Expected: `assets/visual/dsub9_female_visual_centered.stl` is created and its test passes.

- [ ] **Step 4: Export the male STEP from SolidWorks 2023**

Open `DSub9_Male_TwoStageRearShell_V3.step`, select millimetres, binary STL, fine tessellation with maximum chord deviation `0.01 mm` and maximum angle `5 degrees`, and export without applying an extra coordinate transform because the STEP is already centred. Save only to `assets/visual/dsub9_male_visual_centered.stl`. Record the exact SolidWorks export options and SolidWorks build number in `reports/solidworks_export_settings.md`.

- [ ] **Step 5: Validate the male export before accepting it**

```powershell
& $projectPython -m tools.mesh.normalize_visual_meshes --validate-male assets/visual/dsub9_male_visual_centered.stl
& $projectPython -m pytest tests/mesh/test_visual_assets.py -v
```

Expected: both centered bounds tests pass; the male export remains centred and is not scaled by 1000.

---

### Task 3: Parametric collision assets and 32-sided fallback

**Files:**
- Create: `tools/mesh/primitives.py`
- Create: `tools/mesh/section.py`
- Create: `tools/mesh/generate_collision_assets.py`
- Create: `assets/collision/d_guide_male_*.stl`
- Create: `assets/collision/d_socket_female_*.stl`
- Create: `assets/collision/hole_fallback_32_*.stl`
- Create: `tests/mesh/test_collision_assets.py`

**Interfaces:**
- Consumes: centred visual STL meshes and documented pin-hole dimensions.
- Produces: `section_loops(mesh: StlMesh, z_mm: float, tolerance_mm: float) -> tuple[np.ndarray, ...]`, `select_centered_d_loops(loops: tuple[np.ndarray, ...]) -> tuple[np.ndarray, np.ndarray]`, `make_prism(profile_xy: np.ndarray, z0_mm: float, z1_mm: float) -> StlMesh`, `make_annular_sector(inner_radius_mm: float, outer_radius_mm: float, angle0_rad: float, angle1_rad: float, z0_mm: float, z1_mm: float) -> StlMesh`, and named closed convex STL parts.

- [ ] **Step 1: Write failing convex-part tests**

```python
def test_each_collision_part_is_closed_and_non_degenerate():
    for path in generated_collision_paths():
        mesh = read_binary_stl(path)
        assert mesh.triangles.shape[0] >= 12
        assert np.all(mesh.bounds.size > 0)
        assert every_undirected_edge_occurs_twice(mesh)


def test_32_sided_hole_error_is_below_three_microns():
    radius = 0.575
    error = radius * (1 / np.cos(np.pi / 32) - 1)
    assert error < 0.003


def test_section_extraction_finds_centered_d_loops():
    mesh = read_binary_stl(VISUAL / "dsub9_female_visual_centered.stl")
    loops = section_loops(mesh, z_mm=0.50, tolerance_mm=1e-5)
    outer, inner = select_centered_d_loops(loops)
    assert abs(polygon_centroid(outer)[0]) < 1e-4
    assert abs(polygon_centroid(inner)[1]) < 1e-4
    assert abs(polygon_area(outer)) > abs(polygon_area(inner))
```

- [ ] **Step 2: Run tests and verify missing generators fail**

```powershell
& $projectPython -m pytest tests/mesh/test_collision_assets.py -v
```

Expected: import failure for `tools.mesh.primitives`.

- [ ] **Step 3: Implement mesh-section extraction**

Intersect every triangle with the plane `z=z_mm`, discard coplanar duplicates, snap endpoints within `tolerance_mm`, and chain segments into closed loops. Select D-profile loops by requiring the polygon centroid to lie within `0.05 mm` of the task axis and ranking the remaining loops by absolute enclosed area. Preserve the source tessellation around curved corners instead of replacing it with undocumented nominal dimensions.

- [ ] **Step 4: Implement watertight prism and annular-sector generators**

Triangulate front and rear faces with consistent winding, add side quads as two triangles, reject repeated adjacent profile points, and recompute outward normals. The annular-sector generator must create one convex wedge per sector; never combine all 32 wedges into a single concave mesh.

```python
def make_annular_sector(inner_radius_mm, outer_radius_mm, angle0_rad,
                        angle1_rad, z0_mm, z1_mm) -> StlMesh:
    if not 0 < inner_radius_mm < outer_radius_mm:
        raise ValueError("expected 0 < inner radius < outer radius")
    if not angle0_rad < angle1_rad:
        raise ValueError("sector angle must increase")
    # Four XY corners at inner/outer radii are extruded between z0 and z1.
```

- [ ] **Step 5: Generate D-profile components and fallback holes**

Extract the mating-region D loops from the centred visual meshes, pair corresponding points by arc length, and create one closed convex wall prism per paired loop segment. Generate 32 convex annular sectors for each of the nine fallback holes, with separate 0.25 mm entrance and 4.25 mm main-bore depths so the two diameters are represented explicitly.

```powershell
& $projectPython -m tools.mesh.generate_collision_assets
```

- [ ] **Step 6: Run collision-asset tests**

```powershell
& $projectPython -m pytest tests/mesh/test_collision_assets.py -v
```

Expected: every generated part is closed and non-degenerate; the fallback radial discretisation error is below 0.003 mm.

---

### Task 4: Analytic circular-hole SDF plugin

**Files:**
- Create: `plugins/dsub9_hole_sdf/CMakeLists.txt`
- Create: `plugins/dsub9_hole_sdf/hole_sdf.h`
- Create: `plugins/dsub9_hole_sdf/hole_sdf.cc`
- Create: `plugins/dsub9_hole_sdf/register.cc`
- Create: `plugins/dsub9_hole_sdf/README.md`
- Create: `tools/sdf/hole_reference.py`
- Create: `tests/sdf/test_hole_reference.py`
- Create: `tests/sdf/test_plugin_build.py`

**Interfaces:**
- Consumes: point `[x, y, z]` in metres and attributes `bore_radius`, `entry_radius`, `entry_depth`, `bore_depth`, and `outer_radius`.
- Produces: analytic `Distance(point) -> mjtNum`, `Gradient(point, gradient) -> void`, a shared plugin named `mujoco.sdf.dsub9_hole`, and Python reference functions `hole_distance(point_m: np.ndarray, params: HoleParams) -> float` and `hole_gradient(...) -> np.ndarray`.

- [ ] **Step 1: Write failing analytic-geometry tests**

```python
PARAMS = HoleParams(
    bore_radius=0.000575,
    entry_radius=0.000675,
    entry_depth=0.00025,
    bore_depth=0.00450,
    outer_radius=0.00100,
)


def test_axis_is_free_space_inside_bore():
    assert hole_distance(np.array([0.0, 0.0, 0.002]), PARAMS) > 0.0


def test_main_bore_wall_is_zero_level_set():
    assert abs(hole_distance(np.array([0.000575, 0.0, 0.002]), PARAMS)) < 1e-12


def test_entry_section_uses_larger_radius():
    assert hole_distance(np.array([0.000625, 0.0, 0.00010]), PARAMS) > 0.0
    assert hole_distance(np.array([0.000625, 0.0, 0.00050]), PARAMS) < 0.0


def test_gradient_matches_central_difference():
    point = np.array([0.00059, 0.00002, 0.002])
    numerical = central_difference(lambda p: hole_distance(p, PARAMS), point)
    analytic = hole_gradient(point, PARAMS)
    np.testing.assert_allclose(analytic, numerical, atol=1e-5)
```

- [ ] **Step 2: Run reference tests and verify failure**

```powershell
& $projectPython -m pytest tests/sdf/test_hole_reference.py -v
```

Expected: import failure because `tools.sdf.hole_reference` does not exist.

- [ ] **Step 3: Implement the Python reference SDF**

Represent solid material as the union of two finite annuli: an entrance annulus with inner radius `entry_radius` over `z=[0,entry_depth]`, and a main-bore annulus with inner radius `bore_radius` over `z=[entry_depth,bore_depth]`. Construct each finite annulus with exact signed-distance CSG intersections and combine them with `min(entry_distance, main_distance)`. Return positive distance in free bore space and negative distance inside solid material consistently with the plugin implementation.

```python
def hole_distance(point: np.ndarray, params: HoleParams) -> float:
    entry = finite_annulus_distance(
        point, params.entry_radius, params.outer_radius, 0.0, params.entry_depth
    )
    main = finite_annulus_distance(
        point, params.bore_radius, params.outer_radius,
        params.entry_depth, params.bore_depth,
    )
    return min(entry, main)
```

- [ ] **Step 4: Implement the C++ SDF plugin using the same equations**

`hole_sdf.h` contains the parameter struct and pure distance/gradient helpers. `hole_sdf.cc` implements MuJoCo plugin lifecycle methods and validates all five attributes. `register.cc` exports plugin registration. The plugin must reject `bore_radius >= entry_radius`, `entry_radius >= outer_radius`, `entry_depth <= 0`, and `entry_depth >= bore_depth`.

- [ ] **Step 5: Configure and build against the installed MuJoCo package**

```powershell
$mujocoRoot = & $projectPython -c "import pathlib,mujoco; print(pathlib.Path(mujoco.__file__).resolve().parent)"
cmake -S plugins/dsub9_hole_sdf -B build/dsub9_hole_sdf -DMUJOCO_ROOT="$mujocoRoot"
cmake --build build/dsub9_hole_sdf --config Release
```

Expected: a Windows shared library for `mujoco.sdf.dsub9_hole` is produced under `build/dsub9_hole_sdf/Release/`.

- [ ] **Step 6: Add build and symbol-loading test**

```python
def test_plugin_library_exists_and_loads():
    library = plugin_library_path()
    assert library.is_file()
    ctypes.WinDLL(str(library))
```

- [ ] **Step 7: Run SDF tests**

```powershell
& $projectPython -m pytest tests/sdf/test_hole_reference.py tests/sdf/test_plugin_build.py -v
```

Expected: analytic reference tests pass, gradient matches finite differences, and the plugin DLL loads.

---

### Task 5: MuJoCo pair model with analytic pins and SDF holes

**Files:**
- Create: `models/dsub9_pair.xml`
- Create: `models/includes/dsub9_visual.xml`
- Create: `models/includes/dsub9_collision.xml`
- Create: `tools/model/generate_mjcf.py`
- Create: `tests/model/test_mjcf_structure.py`
- Create: `tests/model/test_mjcf_load.py`

**Interfaces:**
- Consumes: centred visual STL files, D-profile collision parts, hole SDF plugin, and documented pin array.
- Produces: `pin_centres_m() -> tuple[tuple[float, float], ...]`, `build_pair_xml(collision_mode: Literal["sdf", "polygon32"]) -> str`, and a loadable `models/dsub9_pair.xml`.

- [ ] **Step 1: Write failing array and XML tests**

```python
def test_pin_centres_form_five_plus_four_pattern():
    centres = pin_centres_m()
    assert len(centres) == 9
    assert sorted(y for _, y in centres).count(0.00142) == 5
    assert sorted(y for _, y in centres).count(-0.00142) == 4
    assert max(x for x, _ in centres) - min(x for x, _ in centres) == pytest.approx(0.01108)


def test_visual_meshes_are_collision_disabled():
    root = ET.parse(MODEL).getroot()
    for geom in root.findall(".//geom[@group='visual']"):
        assert geom.attrib["contype"] == "0"
        assert geom.attrib["conaffinity"] == "0"


def test_model_contains_nine_pins_and_nine_holes():
    root = ET.parse(MODEL).getroot()
    assert len(root.findall(".//geom[@class='pin_collision']")) == 9
    assert len(root.findall(".//geom[@class='hole_sdf_collision']")) == 9
```

- [ ] **Step 2: Verify model tests fail before generation**

```powershell
& $projectPython -m pytest tests/model/test_mjcf_structure.py -v
```

Expected: missing module/model failures.

- [ ] **Step 3: Implement deterministic MJCF generation**

Use exact metre positions. Each pin is `type="cylinder" size="0.0005 0.002"` centred at Z `0.002`. Each SDF instance uses the same XY centre and parameters from Task 4. The female is fixed; the male body has a free joint for contact tests. Use explicit mass and inertia on the male validation body so visual meshes never affect dynamics.

```xml
<geom name="pin_1" class="pin_collision" type="cylinder"
      size="0.0005 0.002" pos="-0.00554 0.00142 0.002"/>
```

- [ ] **Step 4: Generate and structurally validate both collision modes**

```powershell
& $projectPython -m tools.model.generate_mjcf --collision-mode sdf --output models/dsub9_pair.xml
& $projectPython -m tools.model.generate_mjcf --collision-mode polygon32 --output build/dsub9_pair_polygon32.xml
& $projectPython -m pytest tests/model/test_mjcf_structure.py -v
```

- [ ] **Step 5: Add MuJoCo compilation smoke test**

```python
def test_pair_model_compiles():
    model = mujoco.MjModel.from_xml_path(str(MODEL))
    assert model.ngeom > 18
    assert model.nbody >= 3
```

- [ ] **Step 6: Run model load tests**

```powershell
& $projectPython -m pytest tests/model/test_mjcf_structure.py tests/model/test_mjcf_load.py -v
```

Expected: the SDF model compiles, all visual geoms are collision-disabled, and exactly nine pin/hole collision geoms exist.

---

### Task 6: Contact validation scenarios

**Files:**
- Create: `tools/validation/run_contact_cases.py`
- Create: `tests/contact/test_contact_cases.py`
- Create: `tests/contact/test_timestep_sensitivity.py`
- Create: `reports/contact_validation_results.json`
- Create: `reports/collision_geometry_report.md`

**Interfaces:**
- Consumes: `models/dsub9_pair.xml` and generated polygon fallback model.
- Produces: `run_case(case: ContactCase, timestep_s: float, collision_mode: str) -> ContactResult` and machine-readable validation results containing termination, depth, force, torque, contacts, penetration estimate, and runtime.

- [ ] **Step 1: Write failing separation and aligned-insertion tests**

```python
def test_separated_pose_has_no_contacts():
    result = run_case(ContactCase.separated(), 0.0002, "sdf")
    assert result.max_contacts == 0


def test_aligned_quasistatic_insertion_reaches_depth():
    result = run_case(ContactCase.aligned(), 0.0002, "sdf")
    assert result.termination == "SUCCESS"
    assert result.final_depth_m >= 0.0039
    assert np.isfinite(result.peak_force_n)
```

- [ ] **Step 2: Run tests and verify missing runner failure**

```powershell
& $projectPython -m pytest tests/contact/test_contact_cases.py -v
```

Expected: import failure for the contact runner.

- [ ] **Step 3: Implement deterministic quasi-static cases**

Implement separated, aligned, positive/negative X offset, positive/negative Y offset, positive/negative roll/pitch, and two combined offset-plus-tilt cases. Drive the male pose with small bounded increments; collect contacts and six-axis wrench every simulation step; use a single termination reason from `SUCCESS`, `NO_PROGRESS`, `EXCESS_PENETRATION`, or `NUMERICAL_ERROR`.

```python
@dataclass(frozen=True)
class Wrench:
    fx: float
    fy: float
    fz: float
    tx: float
    ty: float
    tz: float


@dataclass(frozen=True)
class ContactResult:
    termination: str
    final_depth_m: float
    peak_force_n: float
    peak_torque_nm: float
    peak_signed_wrench: Wrench
    max_contacts: int
    max_penetration_m: float
    runtime_s: float
```

- [ ] **Step 4: Add directional-contact assertions**

```python
@pytest.mark.parametrize(
    "case, expected_force_axis, expected_sign",
    [
        (ContactCase.x_offset(+0.00010), "fx", -1),
        (ContactCase.x_offset(-0.00010), "fx", +1),
        (ContactCase.y_offset(+0.00010), "fy", -1),
        (ContactCase.y_offset(-0.00010), "fy", +1),
    ],
)
def test_offset_contact_force_opposes_offset(case, expected_force_axis, expected_sign):
    result = run_case(case, 0.0002, "sdf")
    assert np.sign(getattr(result.peak_signed_wrench, expected_force_axis)) == expected_sign
```

- [ ] **Step 5: Add timestep and fallback comparisons**

```python
def test_halving_timestep_does_not_reverse_outcome():
    coarse = run_case(ContactCase.combined(), 0.0002, "sdf")
    fine = run_case(ContactCase.combined(), 0.0001, "sdf")
    assert coarse.termination == fine.termination
    assert np.sign(coarse.peak_signed_wrench.tx) == np.sign(fine.peak_signed_wrench.tx)


def test_sdf_and_polygon_models_agree_on_primary_contact_direction():
    sdf = run_case(ContactCase.x_offset(+0.00010), 0.0002, "sdf")
    polygon = run_case(ContactCase.x_offset(+0.00010), 0.0002, "polygon32")
    assert np.sign(sdf.peak_signed_wrench.fx) == np.sign(polygon.peak_signed_wrench.fx)
```

- [ ] **Step 6: Run the full collision validation suite**

```powershell
& $projectPython -m pytest tests/mesh tests/sdf tests/model tests/contact -v
& $projectPython -m tools.validation.run_contact_cases --all --output reports/contact_validation_results.json
```

Expected: no NaN/Inf, no false contact while separated, aligned insertion succeeds, offset forces oppose offsets, tilt produces a repeatable torque direction, and timestep halving does not reverse the main outcome.

- [ ] **Step 7: Write the geometry and contact report from actual outputs**

`reports/collision_geometry_report.md` must list source hashes, source/derived bounds, the female translation, SolidWorks export settings, pin-hole dimensions, SDF equations and parameters, fallback error, test commands, pass/fail counts, runtime comparison, observed limitations, and the explicit statement that real insertion force is uncalibrated.

---

### Task 7: Final reproducibility audit

**Files:**
- Create: `README.md`
- Create: `.gitignore`
- Create: `reports/final_file_manifest.txt`
- Modify: `reports/collision_geometry_report.md`

**Interfaces:**
- Consumes: all prior outputs.
- Produces: one-command setup, generation, test instructions, and a final manifest with SHA-256 hashes for generated assets.

- [ ] **Step 1: Add exact Windows setup and execution commands**

```powershell
$projectPython = 'C:\Users\ok everything\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $projectPython -m pip install -e '.[test]'
& $projectPython -m tools.mesh.normalize_visual_meshes --female
& $projectPython -m tools.mesh.generate_collision_assets
& $projectPython -m tools.model.generate_mjcf --collision-mode sdf --output models/dsub9_pair.xml
& $projectPython -m pytest -v
```

- [ ] **Step 2: Ignore generated caches but retain reviewed assets**

`.gitignore` includes `.pytest_cache/`, `__pycache__/`, `*.pyc`, `build/`, and temporary validation renders. It must not ignore `assets/visual/`, `assets/collision/`, `models/`, or `reports/`.

- [ ] **Step 3: Generate the final manifest**

Use PowerShell `Get-FileHash -Algorithm SHA256` over every reviewed file under `assets/`, `models/`, `plugins/`, `tools/`, `tests/`, and `reports/`; write sorted relative paths and hashes to `reports/final_file_manifest.txt` through the project reporting utility, not shell redirection.

- [ ] **Step 4: Run final verification from a clean Python process**

```powershell
& $projectPython -m pytest -v
& $projectPython -m tools.validation.run_contact_cases --all --output reports/contact_validation_results.json
```

Expected: all tests pass, the report JSON is regenerated, and source CAD/STL hashes are unchanged.

- [ ] **Step 5: Review final scope and evidence**

Confirm that the report does not claim calibrated force fidelity, that all nine pin-hole pairs are active, that SDF is the formal model, that polygon32 is labelled as fallback, and that no controller or reinforcement-learning code was added.
