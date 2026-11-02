# D-sub9 Chinese Visual Package Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and publish a directly usable Chinese visual delivery package for the reviewed D-sub9 SDF and polygon32 models without changing baseline physics or reviewed contact data.

**Architecture:** A shared Python runtime owns project discovery, model/plugin loading, prescribed poses, Chinese labels, fonts, and immutable-input checks. Thin CLIs reuse that runtime to launch the viewer, render six annotated screenshots, plot schema-3 results, and create a Pillow GIF; the checked-in delivery directory contains launchers, generated media, CSV, and a detailed Chinese guide.

**Tech Stack:** Python 3.13.5, MuJoCo 3.9.0, NumPy, Matplotlib, Pillow, pytest, Windows CMD/PowerShell, Git.

**Spec:** `docs/superpowers/specs/2026-08-25-dsub9-chinese-visual-package-design.md`

## Global Constraints

- Work only on `feature/dsub9-chinese-visual-package`, based on `ea00720f64a088ea86008fc03b8fdc218d214421`.
- Use `D:\KEYANRUJIAN\python.exe`; do not install large software or write new dependencies to C:.
- Do not modify the reviewed collision assets, SDF equations, baseline contact parameters, model XML physics, or `reports/contact_validation_results.json`.
- The contact-results SHA-256 must remain `ac767ea63a7e8a6866a974728a1256e688832003076170e270cd181e5c9d65ff`.
- Formal SDF loading must register `build/dsub9_hole_sdf/Release/dsub9_hole_sdf.dll` from the project-root current directory through its ASCII relative path.
- polygon32 must not load the SDF plugin and must be described as an approximation.
- Rendering may receive one evidence-based environment repair attempt; after that use the documented viewer fallback or report the blocker.
- Use a GIF because FFmpeg is unavailable and Pillow is installed.
- Run only focused tests during development and one full pytest run after final artifact generation.
- Use one main agent sequentially; do not dispatch subagents.
- Do not merge the delivery branch into `main`; push the reviewed baseline and delivery branch only after final verification.

## Planned File Structure

- `tools/visualization/runtime.py`: project paths, model modes, plugin loading, prescribed poses, immutable-input hashing.
- `tools/visualization/font_support.py`: deterministic Chinese font discovery and Pillow/Matplotlib font configuration.
- `tools/visualization/launch_viewer.py`: preflight checks, fallback generation, `--check-only`, and interactive viewer entry point.
- `tools/visualization/render_scenes.py`: MuJoCo offscreen frames, display-only colors/groups, Chinese annotation, and six PNG outputs.
- `tools/visualization/plot_contact_results.py`: schema-3 validation, unique result labels, three charts, and summary CSV.
- `tools/visualization/make_pose_sweep_animation.py`: prescribed pose sequence and annotated GIF generation.
- `tests/visualization/`: focused unit and integration tests for the files above and final artifacts.
- `deliverables/chinese_visual_package/`: user-facing guide, two CMD launchers, screenshots, charts, CSV, and GIF.
- `tools/reporting/generate_manifest.py`: include `docs/`, `deliverables/`, and the tracked handoff document.
- `tests/reporting/test_manifest.py`: prove the expanded manifest coverage.
- `pyproject.toml`: declare the visualization extra used on a new machine.

---

### Task 1: Shared Runtime and Prescribed Poses

**Files:**
- Create: `tools/visualization/__init__.py`
- Create: `tools/visualization/runtime.py`
- Create: `tests/visualization/__init__.py`
- Create: `tests/visualization/test_runtime.py`

**Interfaces:**
- Consumes: reviewed XMLs, SDF DLL, and `tools.model.generate_mjcf`.
- Produces: `CollisionMode`, `PoseCase`, `PROJECT_ROOT`, `find_project_root(start)`, `load_model(mode)`, `apply_pose(model, data, pose)`, `input_hashes()`.

- [ ] **Step 1: Write failing project-discovery and pose tests**

```python
def test_find_project_root_from_delivery_subdirectory():
    start = PROJECT_ROOT / "deliverables" / "chinese_visual_package"
    assert find_project_root(start) == PROJECT_ROOT

def test_pose_sets_free_joint_without_stepping_dynamics():
    model = load_model("polygon32")
    data = mujoco.MjData(model)
    apply_pose(model, data, POSE_CASES["x_offset_pos_100um"])
    assert data.qpos[0] == pytest.approx(0.0001)
    assert data.qpos[2] == pytest.approx(0.0)
    assert data.time == 0.0
```

- [ ] **Step 2: Run the focused tests and confirm missing-module failure**

Run: `& 'D:\KEYANRUJIAN\python.exe' -m pytest tests/visualization/test_runtime.py -v`

Expected: collection fails because `tools.visualization.runtime` does not exist.

- [ ] **Step 3: Implement root discovery, model modes, and immutable paths**

```python
CollisionMode = Literal["sdf", "polygon32"]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
FORMAL_MODEL = Path("models/dsub9_pair.xml")
FALLBACK_MODEL = Path("build/dsub9_pair_polygon32.xml")
PLUGIN_RELATIVE_PATH = Path("build/dsub9_hole_sdf/Release/dsub9_hole_sdf.dll")

def find_project_root(start: Path) -> Path:
    for candidate in (start.resolve(), *start.resolve().parents):
        if (candidate / "pyproject.toml").is_file() and (candidate / FORMAL_MODEL).is_file():
            return candidate
    raise FileNotFoundError("无法定位项目根目录：未同时找到 pyproject.toml 和正式模型。")
```

- [ ] **Step 4: Implement exact plugin/model loading and pose application**

```python
@contextmanager
def project_root_cwd(root: Path = PROJECT_ROOT):
    previous = Path.cwd()
    os.chdir(root)
    try:
        yield
    finally:
        os.chdir(previous)

def load_model(mode: CollisionMode) -> mujoco.MjModel:
    relative = FORMAL_MODEL if mode == "sdf" else FALLBACK_MODEL
    if mode == "sdf":
        with project_root_cwd():
            mujoco.mj_loadPluginLibrary(PLUGIN_RELATIVE_PATH.as_posix())
    with project_root_cwd():
        return mujoco.MjModel.from_xml_path(relative.as_posix())

def apply_pose(model: mujoco.MjModel, data: mujoco.MjData, pose: PoseCase) -> None:
    data.qpos[:3] = (pose.x_offset_m, pose.y_offset_m, pose.origin_z_m)
    data.qpos[3:7] = pose.quaternion_wxyz()
    mujoco.mj_forward(model, data)
```

- [ ] **Step 5: Add a fresh-process test proving SDF registers and polygon32 does not**

Use a subprocess with `cwd=PROJECT_ROOT`, call `load_model(sys.argv[1])`, and print JSON containing `model.nplugin`. Assert `sdf` returns `1` and `polygon32` returns `0` in separate processes.

- [ ] **Step 6: Run Task 1 tests**

Run: `& 'D:\KEYANRUJIAN\python.exe' -m pytest tests/visualization/test_runtime.py tests/model/test_mjcf_load.py -v`

Expected: all selected tests pass.

- [ ] **Step 7: Commit Task 1**

```powershell
git --git-dir='D:\dsub9项目计划\first_stage_sim_gitdata' --work-tree='D:\dsub9项目计划\first_stage_sim' add tools/visualization tests/visualization
git --git-dir='D:\dsub9项目计划\first_stage_sim_gitdata' --work-tree='D:\dsub9项目计划\first_stage_sim' commit -m "feat: add shared visualization runtime"
```

### Task 2: Chinese Fonts and Contact-Result Charts

**Files:**
- Create: `tools/visualization/font_support.py`
- Create: `tools/visualization/plot_contact_results.py`
- Create: `tests/visualization/test_contact_plots.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: `reports/contact_validation_results.json` schema 3.
- Produces: `find_chinese_font() -> Path`, `load_result_rows(path) -> list[ResultRow]`, `write_summary_csv(rows, path)`, `generate_charts(input_path, output_dir)`.

- [ ] **Step 1: Write failing schema, grouping, CSV, font, and disclaimer tests**

```python
def test_schema3_creates_twenty_rows_with_exact_profile_counts():
    rows = load_result_rows(RESULTS)
    assert len(rows) == 20
    assert Counter(row.contact_profile for row in rows) == {
        "uncalibrated_diagnostic_v1": 16,
        "uncalibrated_low_response_v1": 2,
        "uncalibrated_high_response_v1": 2,
    }

def test_every_result_label_is_unique():
    labels = [row.display_label for row in load_result_rows(RESULTS)]
    assert len(labels) == len(set(labels)) == 20
```

Also assert a bad `schema_version` raises `ValueError`, the CSV has 20 data rows and the required Chinese headers, and each generated PNG contains metadata key `Disclaimer` with `未经过实物标定`.

- [ ] **Step 2: Run tests and confirm missing-module failure**

Run: `& 'D:\KEYANRUJIAN\python.exe' -m pytest tests/visualization/test_contact_plots.py -v`

- [ ] **Step 3: Implement deterministic Chinese-font selection**

```python
PREFERRED_FONTS = ("Noto Sans SC", "Microsoft YaHei", "SimHei", "SimSun")

def find_chinese_font() -> Path:
    by_name = {item.name: Path(item.fname) for item in font_manager.fontManager.ttflist}
    for name in PREFERRED_FONTS:
        if name in by_name and by_name[name].is_file():
            return by_name[name]
    raise RuntimeError("未找到可用中文字体；已检查 Noto Sans SC、微软雅黑、黑体和宋体。")
```

- [ ] **Step 4: Implement strict schema-3 rows and unique display labels**

Define `ResultRow` with the exact JSON fields `case`, `collision_mode`, `contact_profile`, `termination`, `peak_force_n`, `peak_torque_nm`, `max_penetration_m`, `timestep_s`, and `spatial_step_m`. Map case/profile/mode to Chinese; append timestep and spatial step when duplicate case/mode/profile combinations occur.

- [ ] **Step 5: Implement CSV and three horizontal bar charts**

Use `csv.DictWriter(..., encoding="utf-8-sig")`, separate baseline from two sensitivity profiles by color and legend, convert penetration from metres to micrometres, and place `未经过实物标定，仅用于数值敏感性分析` below every chart.

- [ ] **Step 6: Declare portable visualization dependencies**

Add to `pyproject.toml`:

```toml
visualization = [
    "matplotlib>=3.9",
    "pillow>=10",
]
```

under `[project.optional-dependencies]`, without installing anything.

- [ ] **Step 7: Run Task 2 tests and generate temporary outputs**

Run: `& 'D:\KEYANRUJIAN\python.exe' -m pytest tests/visualization/test_contact_plots.py -v`

Run: `& 'D:\KEYANRUJIAN\python.exe' -m tools.visualization.plot_contact_results --output-dir tmp/visual-charts`

Expected: three readable PNG files and one CSV; the source JSON hash is unchanged.

- [ ] **Step 8: Commit Task 2**

Commit message: `feat: generate Chinese contact result charts`.

### Task 3: Viewer CLI and Two Double-Click Launchers

**Files:**
- Create: `tools/visualization/launch_viewer.py`
- Create: `tests/visualization/test_launch_viewer.py`
- Create: `deliverables/chinese_visual_package/启动正式SDF场景.cmd`
- Create: `deliverables/chinese_visual_package/启动免插件场景.cmd`

**Interfaces:**
- Consumes: `runtime.load_model`, fallback generator, and `mujoco.viewer`.
- Produces: `preflight(mode) -> list[str]`, CLI options `--mode {sdf,polygon32}` and `--check-only`.

- [ ] **Step 1: Write failing launcher preflight and CMD-content tests**

```python
def test_check_only_compiles_formal_model_without_opening_viewer():
    result = run_launcher("sdf", "--check-only")
    assert result.returncode == 0
    assert "正式 SDF 模型检查通过" in result.stdout

def test_fallback_cmd_never_requests_sdf_mode():
    text = FALLBACK_CMD.read_text(encoding="utf-8")
    assert "--mode polygon32" in text
    assert "--mode sdf" not in text
```

- [ ] **Step 2: Run tests and confirm failure**

Run: `& 'D:\KEYANRUJIAN\python.exe' -m pytest tests/visualization/test_launch_viewer.py -v`

- [ ] **Step 3: Implement preflight and fallback generation**

For SDF, check the DLL and formal XML before `load_model("sdf")`. For polygon32, generate a missing XML with `generate_model("polygon32", FALLBACK_MODEL)` and never call plugin registration. Validate `female_visual`, `male_visual`, `pin_01`, `pin_09`, and representative hole/guide geoms after compilation.

- [ ] **Step 4: Implement check-only and interactive modes**

```python
if args.check_only:
    print("正式 SDF 模型检查通过" if args.mode == "sdf" else "免插件 polygon32 模型检查通过")
    return 0
data = mujoco.MjData(model)
apply_pose(model, data, POSE_CASES["aligned"])
with mujoco.viewer.launch_passive(model, data) as viewer:
    while viewer.is_running():
        viewer.sync()
        time.sleep(0.02)
```

- [ ] **Step 5: Create UTF-8 Chinese CMD launchers with failure pause**

Each file starts with `@echo off`, `chcp 65001 >nul`, derives the repository root from `%~dp0..\..\`, checks `D:\KEYANRUJIAN\python.exe`, runs `-m tools.visualization.launch_viewer`, and executes `pause` only when `errorlevel 1`.

- [ ] **Step 6: Run both noninteractive real checks**

Run: `& 'D:\KEYANRUJIAN\python.exe' -m tools.visualization.launch_viewer --mode sdf --check-only`

Run: `& 'D:\KEYANRUJIAN\python.exe' -m tools.visualization.launch_viewer --mode polygon32 --check-only`

Expected: both compile; only the formal child registers the plugin.

- [ ] **Step 7: Commit Task 3**

Commit message: `feat: add one-click MuJoCo launchers`.

### Task 4: Six Annotated Scene Screenshots

**Files:**
- Create: `tools/visualization/render_scenes.py`
- Create: `tests/visualization/test_render_scenes.py`
- Generate: `deliverables/chinese_visual_package/screenshots/*.png`

**Interfaces:**
- Consumes: runtime models/poses and `font_support.find_chinese_font`.
- Produces: `render_frame(mode, pose, camera, display) -> Image.Image`, `generate_screenshots(output_dir) -> list[Path]`.

- [ ] **Step 1: Write failing output-contract and immutable-input tests**

Assert the six exact filenames, PNG format, width at least 1600, height at least 900, non-empty pixel variance, and embedded `Title` metadata. Hash formal XML, JSON, and every file under `assets/collision/` before and after generation and assert equality.

- [ ] **Step 2: Run tests and confirm missing renderer failure**

Run: `& 'D:\KEYANRUJIAN\python.exe' -m pytest tests/visualization/test_render_scenes.py -v`

- [ ] **Step 3: Implement offscreen MuJoCo rendering with in-memory display styling**

Set `model.vis.global_.offwidth = 1600` and `offheight = 900` before constructing `mujoco.Renderer`. For overlay views, copy and change only in-memory `model.geom_rgba`: visual geoms become semi-transparent, pins are orange, hole geoms blue, male guide green, and female socket magenta. Keep `geom_contype`, `geom_conaffinity`, friction, solref, solimp, and margin unchanged.

- [ ] **Step 4: Implement fixed cameras and Chinese annotation**

Define named `mujoco.MjvCamera` presets for overview, front-array close-up, and oblique collision overlay. Use Pillow to add a top title band and bottom caption band with the selected Chinese font; save PNG metadata keys `Title`, `Caption`, `ModelMode`, and `GenerationMethod`.

- [ ] **Step 5: Implement the six required render recipes**

Generate the exact filenames from the handoff. The comparison image renders SDF and polygon32 separately with the same pose/camera, resizes each to 800×760, joins them side by side, and labels the right panel `polygon32 近似回退模型（非解析圆孔）`.

- [ ] **Step 6: Run one real generation attempt and focused tests**

Run: `& 'D:\KEYANRUJIAN\python.exe' -m tools.visualization.render_scenes --output-dir deliverables/chinese_visual_package/screenshots`

If it fails, capture the backend exception, test one environment correction, and rerun once. Do not begin a second repair cycle.

- [ ] **Step 7: Commit Task 4**

Commit message: `feat: render annotated D-sub9 scene images`.

### Task 5: Quasi-Static Pose-Sweep GIF

**Files:**
- Create: `tools/visualization/make_pose_sweep_animation.py`
- Create: `tests/visualization/test_pose_animation.py`
- Generate: `deliverables/chinese_visual_package/animation/DSub9_准静态位姿扫描.gif`

**Interfaces:**
- Consumes: `render_scenes.render_frame` and runtime poses.
- Produces: `build_pose_sequence(fps=10) -> list[PoseCase]`, `make_animation(output, fps=10) -> Path`.

- [ ] **Step 1: Write failing sequence, disclaimer, duration, and readability tests**

Assert 100–200 frames at 10 fps, 10–20 seconds total duration, first/middle/last frames differ, GIF loop metadata is zero, and OCR-independent PNG/GIF metadata plus a sampled pixel crop prove the disclaimer band exists on every generated frame.

- [ ] **Step 2: Run tests and confirm failure**

Run: `& 'D:\KEYANRUJIAN\python.exe' -m pytest tests/visualization/test_pose_animation.py -v`

- [ ] **Step 3: Implement deterministic prescribed-pose interpolation**

Build 120 frames: 50 frames move origin Z from -0.005 m to 0 m while aligned, 20 hold aligned, 20 hold +100 µm X offset, 20 interpolate to combined A, and 10 hold combined A. Interpolate position and roll/pitch parameters, then recompute normalized quaternions; call only `mj_forward`, never `mj_step`.

- [ ] **Step 4: Render and save a Pillow GIF**

Add the fixed text `准静态规定姿态扫描演示；不是自由动力学插入，不包含机器人或力控制器。` to every frame and save with `duration=100`, `loop=0`, and `optimize=False`.

- [ ] **Step 5: Generate and validate the real GIF**

Run: `& 'D:\KEYANRUJIAN\python.exe' -m tools.visualization.make_pose_sweep_animation`

Run: `& 'D:\KEYANRUJIAN\python.exe' -m pytest tests/visualization/test_pose_animation.py -v`

- [ ] **Step 6: Commit Task 5**

Commit message: `feat: add quasi-static pose sweep animation`.

### Task 6: Chinese User Guide and Complete Delivery Contract

**Files:**
- Create: `deliverables/chinese_visual_package/中文使用说明.md`
- Create: `tests/visualization/test_delivery_package.py`
- Generate: `deliverables/chinese_visual_package/charts/*.png`
- Generate: `deliverables/chinese_visual_package/charts/接触结果中文摘要.csv`

**Interfaces:**
- Consumes: every previous CLI and generated artifact.
- Produces: complete user-facing package and machine-checkable artifact contract.

- [ ] **Step 1: Write failing tests for required guide topics and artifacts**

Parameterize all 20 required topics from the handoff and assert each heading or required phrase appears. Assert two CMDs, six screenshots, three charts, one CSV, and one GIF exist; verify all Markdown-relative links resolve from the guide directory.

- [ ] **Step 2: Generate final chart files**

Run: `& 'D:\KEYANRUJIAN\python.exe' -m tools.visualization.plot_contact_results --output-dir deliverables/chinese_visual_package/charts`

- [ ] **Step 3: Write the detailed Chinese guide**

Use 20 numbered sections matching the handoff, embed all six screenshots and three charts with relative Markdown paths, describe the GIF as prescribed-pose visualization, include double-click and command-line workflows, and explain how another computer must update the Python path, install `.[visualization,test]`, build the SDF DLL, and generate the polygon32 XML.

- [ ] **Step 4: Add explicit scientific-limit and next-stage language**

State that force and torque are uncalibrated numerical diagnostics, not physical insertion-force predictions or safety thresholds. Describe robot/force-sensor/compliance/RL integration only as future interfaces requiring a robot model, controller, sensors, calibration, and validation.

- [ ] **Step 5: Run focused delivery tests**

Run: `& 'D:\KEYANRUJIAN\python.exe' -m pytest tests/visualization -v`

Expected: all visualization tests pass with no unexpected skip.

- [ ] **Step 6: Commit Task 6**

Commit message: `docs: complete Chinese visual delivery package`.

### Task 7: Expand and Refresh the Reproducibility Manifest

**Files:**
- Modify: `tools/reporting/generate_manifest.py`
- Modify: `tests/reporting/test_manifest.py`
- Modify: `reports/final_file_manifest.txt`

**Interfaces:**
- Consumes: all final tracked source and delivery files.
- Produces: a deterministic manifest covering `docs/`, `deliverables/`, and `下一任务交接_中文可视化交付包_A方案.md` while excluding itself and caches.

- [ ] **Step 1: Write failing expanded-coverage tests**

Change the fixture roots to include `docs` and `deliverables`, create sample files under both, create the handoff root file, and assert all three paths are present in `build_manifest()`.

- [ ] **Step 2: Run manifest tests and confirm coverage failure**

Run: `& 'D:\KEYANRUJIAN\python.exe' -m pytest tests/reporting/test_manifest.py -v`

- [ ] **Step 3: Expand manifest scope minimally**

```python
REVIEW_DIRECTORIES = (
    "assets", "models", "plugins", "tools", "tests", "reports", "docs", "deliverables"
)
REVIEW_ROOT_FILES = (
    "README.md", "pyproject.toml", ".gitattributes", ".gitignore",
    "下一任务交接_中文可视化交付包_A方案.md",
)
```

- [ ] **Step 4: Run focused manifest and visualization tests**

Run: `& 'D:\KEYANRUJIAN\python.exe' -m pytest tests/reporting/test_manifest.py tests/visualization -v`

- [ ] **Step 5: Refresh the manifest after every other final artifact exists**

Run: `& 'D:\KEYANRUJIAN\python.exe' -m tools.reporting.generate_manifest`

Run: `& 'D:\KEYANRUJIAN\python.exe' -m tools.reporting.generate_manifest --verify`

- [ ] **Step 6: Commit Task 7**

Commit message: `chore: refresh visual package manifest`.

### Task 8: Visual QA, Final Verification, Review, and GitHub Publication

**Files:**
- Inspect: all files under `deliverables/chinese_visual_package/`
- Inspect: all changes from `ea00720..HEAD`
- Modify only files with verified defects found in this task.

**Interfaces:**
- Consumes: complete delivery branch.
- Produces: reviewed commit history, clean worktree, and GitHub branches.

- [ ] **Step 1: Perform visual QA**

Open all nine PNGs and inspect the GIF first, middle, and last frames. Record image dimensions and animation frame count/duration. Confirm Chinese glyphs, 5+4 array visibility, insertion direction, collision colors, equal comparison cameras, units, and disclaimers.

- [ ] **Step 2: Verify protected inputs and generated media mechanically**

Run SHA-256 on `reports/contact_validation_results.json`; compare core XML and collision assets to `ea00720`; use Pillow to load every PNG and every GIF frame; parse the CSV and assert 20 data rows.

- [ ] **Step 3: Run the one allowed complete test suite**

Run: `& 'D:\KEYANRUJIAN\python.exe' -m pytest -ra`

Expected: at least 164 baseline tests plus the new visualization/manifest tests pass, with zero unexpected skips. Record exact count and elapsed time.

- [ ] **Step 4: Refresh manifest only if final-test side effects changed a reviewed file**

If and only if a reviewed artifact changed, regenerate the manifest once and run its `--verify` command. Do not rerun the full suite.

- [ ] **Step 5: Conduct one concentrated review**

Review `git diff ea00720..HEAD` for scope, scientific claims, launcher quoting, plugin isolation, asset immutability, test validity, generated artifact quality, and accidental secrets. Fix confirmed issues, rerun only affected focused tests, and commit the fixes.

- [ ] **Step 6: Confirm repository state**

Verify current branch, `git status --short --branch`, commit log, absence of files larger than GitHub's limit, and no tracked credentials or local paths except the intentionally documented Python path.

- [ ] **Step 7: Configure the GitHub remote**

Add `origin` as `https://github.com/1585700447zym-cell/dsub9-contact-verification.git`, or verify it exactly if already present. Do not overwrite a different remote silently.

- [ ] **Step 8: Publish the stable baseline without merging**

Push local `feature/dsub9-collision-model` to remote `feature/dsub9-collision-model`, and create remote `main` pointing to the exact baseline commit `ea00720`. Verify both remote refs resolve to that commit.

- [ ] **Step 9: Publish the completed delivery branch**

Push `feature/dsub9-chinese-visual-package`, set its upstream, and verify the remote branch resolves to the final local HEAD. If GitHub requests authentication, stop at the credential prompt and give the user the shortest sign-in instruction; never print tokens.

- [ ] **Step 10: Deliver the handoff**

Report the local package path, GitHub repository URL, branch names, final commit, exact test result, manifest status, and the two launchers. State clearly that `main` is the stable baseline and the new package remains on its feature branch pending the user's merge decision.
