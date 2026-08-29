# D-sub9 V1 Contact Validation Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 保留已验收 schema-3 基线不变，新增逐深度六维接触轨迹、固定深度网格时间步收敛验证、中文图表、技术报告和面向初学者的详细使用说明。

**Architecture:** 将现有准静态扫描循环抽取为共享内核，同时支持旧峰值摘要与新 trace 输出。独立的收敛模块只处理已采样 trace，可视化和报告模块只消费结构化 JSON，最终 CLI 组织一条命令生成全部交付。

**Tech Stack:** Python 3.13、MuJoCo 3.9、NumPy、Matplotlib、Pillow、pytest、Markdown、JSON、CSV。

**Spec:** `docs/superpowers/specs/2026-08-29-dsub9-v1-contact-validation-design.md`

## Global Constraints

- 不修改 `models/`、`assets/collision/`、`plugins/dsub9_hole_sdf/` 的受审内容。
- `reports/contact_validation_results.json` 必须保持 schema 3、20 条结果和 SHA-256 `ac767ea63a7e8a6866a974728a1256e688832003076170e270cd181e5c9d65ff`。
- 新 trace 使用正式 SDF、baseline 接触配置、`0.00001 m` 固定深度网格和 `0.0004/0.0002/0.0001 s` 三个时间步。
- 新结果只表示未标定准静态数值诊断，不得称为真实插入力、自由动力学或 RL episode。
- 生成文本使用 UTF-8 与 LF；Excel CSV 使用 UTF-8 with BOM。
- 新 JSON 不允许 NaN/Infinity，且拒绝不支持的 schema。
- 不通过修改门槛、接触参数或删除工况让收敛结果变成 `PASS`。
- 实现分支为 `feature/dsub9-v1-contact-validation`，不自动合并到 `main`。

---

### Task 1: 共享扫描内核与 trace 数据类型

**Files:**
- Create: `tests/contact/test_contact_traces.py`
- Modify: `tools/validation/run_contact_cases.py:55-445`

**Interfaces:**
- Consumes: `ContactCase`, `ContactResult`, `Wrench`, `_load_model`, `_male_world_wrench` from `tools.validation.run_contact_cases`.
- Produces: `ContactSample`, `ContactTrace`, `run_case_trace(...) -> ContactTrace`; preserves `run_case(...) -> ContactResult`.

- [ ] **Step 1: Write failing public-contract tests**

```python
from dataclasses import asdict
import math

import pytest

from tools.validation.run_contact_cases import (
    ContactCase,
    ContactSample,
    ContactTrace,
    run_case,
    run_case_trace,
)


def test_trace_has_monotonic_fixed_grid_and_matching_summary():
    trace = run_case_trace(
        ContactCase.x_offset(+0.00010),
        0.0004,
        "sdf",
        spatial_step_m=0.00001,
    )
    depths = [sample.depth_m for sample in trace.samples]
    assert depths == sorted(depths)
    assert all(
        math.isclose(right - left, 0.00001, abs_tol=1e-15)
        for left, right in zip(depths, depths[1:])
    )
    assert trace.summary.final_depth_m == trace.samples[-1].depth_m
    assert trace.summary.steps == len(trace.samples)
    assert trace.timestep_s == 0.0004
    assert trace.spatial_step_m == 0.00001
    assert set(asdict(trace.samples[0])) == {
        "step_index", "depth_m", "male_origin_z_m", "wrench",
        "force_norm_n", "torque_norm_nm", "contact_count", "penetration_m",
    }


def test_explicit_trace_grid_is_independent_of_timestep():
    coarse = run_case_trace(ContactCase.combined(), 0.0004, "sdf", spatial_step_m=0.00001)
    fine = run_case_trace(ContactCase.combined(), 0.0001, "sdf", spatial_step_m=0.00001)
    common_count = min(len(coarse.samples), len(fine.samples))
    assert [sample.depth_m for sample in coarse.samples[:common_count]] == [
        sample.depth_m for sample in fine.samples[:common_count]
    ]
    assert abs(coarse.summary.final_depth_m - fine.summary.final_depth_m) <= 0.00001


@pytest.mark.parametrize("bad_step", [0.0, -1e-5, float("nan"), float("inf")])
def test_trace_rejects_nonpositive_or_nonfinite_spatial_step(bad_step):
    with pytest.raises(ValueError, match="spatial_step_m"):
        run_case_trace(ContactCase.aligned(), 0.0002, "sdf", spatial_step_m=bad_step)
```

- [ ] **Step 2: Run tests and verify the missing-interface failure**

Run:

```powershell
& 'D:\KEYANRUJIAN\python.exe' -m pytest tests/contact/test_contact_traces.py -q
```

Expected: collection fails because `ContactSample`, `ContactTrace`, and `run_case_trace` do not exist.

- [ ] **Step 3: Implement trace types and one shared sweep function**

Add frozen dataclasses with the exact fields from the spec. Implement a private `_run_sweep(case, timestep_s, collision_mode, *, profile, spatial_step_m, capture_samples)` that owns the current loop. `run_case` passes `DEFAULT_SPEED_M_S * timestep_s` and `capture_samples=False`; `run_case_trace` validates explicit `spatial_step_m` and passes `capture_samples=True`.

```python
@dataclass(frozen=True)
class ContactSample:
    step_index: int
    depth_m: float
    male_origin_z_m: float
    wrench: Wrench
    force_norm_n: float
    torque_norm_nm: float
    contact_count: int
    penetration_m: float


@dataclass(frozen=True)
class ContactTrace:
    case: ContactCase
    collision_mode: str
    contact_profile: str
    timestep_s: float
    spatial_step_m: float
    solver: str
    samples: tuple[ContactSample, ...]
    summary: ContactResult
```

Construct each sample only after finite-state validation. Preserve the current peak replacement rule, termination order, runtime measurement, and solver label.

- [ ] **Step 4: Prove old and new behavior agree**

Add a regression test that runs the same X-offset case through `run_case` and `run_case_trace` with `spatial_step_m=DEFAULT_SPEED_M_S * timestep_s`, removes `runtime_s`, and asserts equal summary dictionaries.

Run:

```powershell
& 'D:\KEYANRUJIAN\python.exe' -m pytest tests/contact/test_contact_traces.py tests/contact/test_contact_cases.py tests/contact/test_timestep_sensitivity.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit the shared sweep**

```powershell
git add tools/validation/run_contact_cases.py tests/contact/test_contact_traces.py
git commit -m "feat: record deterministic contact traces"
```

---

### Task 2: 时间步收敛指标与验收判定

**Files:**
- Create: `tools/validation/v1_convergence.py`
- Create: `tests/contact/test_v1_convergence.py`

**Interfaces:**
- Consumes: `ContactTrace`, `ContactSample`, `Wrench`.
- Produces: `primary_component_for_case(case_name) -> str | None`, `compare_trace(reference, candidate) -> dict`, `build_convergence_document(traces) -> dict`.

- [ ] **Step 1: Write failing metric tests with artificial traces**

Create helpers that construct two three-sample `ContactTrace` objects without MuJoCo. Test:

```python
def test_identical_trace_has_zero_error_and_passes():
    document = build_convergence_document((fine_trace, medium_trace, coarse_trace))
    assert document["schema_version"] == 1
    assert document["overall_status"] == "PASS"
    medium = document["cases"][0]["comparisons"]["0.0002"]
    assert medium["peak_force_relative_error"] == 0.0
    assert medium["primary_component_normalized_rmse"] == 0.0


def test_zero_reference_uses_null_relative_metrics():
    comparison = compare_trace(zero_reference, zero_candidate)
    assert comparison["peak_force_relative_error"] is None
    assert comparison["primary_component_normalized_rmse"] is None
    assert comparison["zero_contact_absolute_pass"] is True


def test_exceeding_frozen_medium_threshold_fails_without_dropping_values():
    comparison = compare_trace(fine_trace, high_error_medium_trace)
    assert comparison["peak_force_relative_error"] > 0.10
    assert comparison["status"] == "FAIL"
```

- [ ] **Step 2: Run tests and verify import failure**

```powershell
& 'D:\KEYANRUJIAN\python.exe' -m pytest tests/contact/test_v1_convergence.py -q
```

Expected: `ModuleNotFoundError` for `tools.validation.v1_convergence`.

- [ ] **Step 3: Implement deterministic comparison rules**

Use `0.0001 s` as reference. Map case families to primary components: X -> `fx`, Y -> `fy`, roll -> `tx`, pitch -> `ty`, combined -> `tx`; aligned has no primary component. Compare only the common depth prefix after verifying equal `spatial_step_m`.

```python
REFERENCE_TIMESTEP_S = 0.0001
MEDIUM_TIMESTEP_S = 0.0002
COARSE_TIMESTEP_S = 0.0004
MEDIUM_RELATIVE_LIMIT = 0.10
COARSE_RELATIVE_LIMIT = 0.20
ZERO_CONTACT_ABS_LIMIT = 1e-12
DEPTH_DELTA_LIMIT_M = 0.00001
```

The comparison `status` is `PASS` only when hard gates and applicable magnitude/RMSE limits pass. Preserve raw metrics even on failure.

- [ ] **Step 4: Test pass, fail, sign reversal, termination mismatch, depth mismatch, and zero-contact branches**

```powershell
& 'D:\KEYANRUJIAN\python.exe' -m pytest tests/contact/test_v1_convergence.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit convergence analysis**

```powershell
git add tools/validation/v1_convergence.py tests/contact/test_v1_convergence.py
git commit -m "feat: evaluate V1 timestep convergence"
```

---

### Task 3: V1 矩阵生成、JSON/CSV 序列化与原子写入

**Files:**
- Create: `tools/validation/run_v1_contact_validation.py`
- Create: `tests/contact/test_v1_contact_outputs.py`

**Interfaces:**
- Consumes: `all_cases`, `run_case_trace`, `build_convergence_document`.
- Produces: `build_trace_document(traces, source_sha256) -> dict`, `write_trace_json`, `write_trace_csv`, `write_convergence_json`, `generate_v1_data() -> tuple[dict, dict]`.

- [ ] **Step 1: Write failing schema and encoding tests**

Use monkeypatched small traces so unit tests do not run the 36-case MuJoCo matrix. Require:

```python
def test_trace_document_has_frozen_schema_and_source_hash():
    document = build_trace_document(traces, "a" * 64)
    assert document["schema_version"] == 1
    assert document["source_contact_results_sha256"] == "a" * 64
    assert document["timestep_values_s"] == [0.0004, 0.0002, 0.0001]
    assert document["spatial_step_m"] == 0.00001
    assert len(document["traces"]) == len(traces)


def test_csv_is_utf8_bom_and_has_flat_wrench_columns(tmp_path):
    output = tmp_path / "trace.csv"
    write_trace_csv(traces, output)
    assert output.read_bytes().startswith(b"\xef\xbb\xbf")
    header = output.read_text(encoding="utf-8-sig").splitlines()[0]
    assert "fx_n" in header and "tz_nm" in header and "penetration_m" in header
```

- [ ] **Step 2: Run tests and verify missing module failure**

```powershell
& 'D:\KEYANRUJIAN\python.exe' -m pytest tests/contact/test_v1_contact_outputs.py -q
```

Expected: import failure for the new module.

- [ ] **Step 3: Implement exact matrix and serializers**

```python
TIMESTEP_VALUES_S = (0.0004, 0.0002, 0.0001)
SPATIAL_STEP_M = 0.00001
TRACE_JSON = ROOT / "reports" / "v1_contact_traces.json"
TRACE_CSV = ROOT / "reports" / "v1_contact_traces.csv"
CONVERGENCE_JSON = ROOT / "reports" / "v1_timestep_convergence.json"
```

Generate `len(all_cases()) * len(TIMESTEP_VALUES_S) == 36` traces in deterministic case-major, timestep-major order. Compute the SHA-256 of the existing schema-3 file from bytes. Write each output to a sibling temporary file, flush and close it, then use `os.replace`.

- [ ] **Step 4: Test rejection of bad schema, NaN, incomplete matrix, and partial writes**

Use `json.dumps(..., allow_nan=False)` and explicit validation that each case has all three timestep keys.

```powershell
& 'D:\KEYANRUJIAN\python.exe' -m pytest tests/contact/test_v1_contact_outputs.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit V1 data generation**

```powershell
git add tools/validation/run_v1_contact_validation.py tests/contact/test_v1_contact_outputs.py
git commit -m "feat: generate V1 trace datasets"
```

---

### Task 4: 中文接触曲线与时间步图表

**Files:**
- Create: `tools/visualization/plot_v1_contact_validation.py`
- Create: `tests/visualization/test_v1_contact_plots.py`

**Interfaces:**
- Consumes: schema-1 trace JSON and convergence JSON.
- Produces: `load_v1_documents(trace_path, convergence_path)`, `generate_v1_charts(trace_path, convergence_path, output_dir) -> list[Path]`.

- [ ] **Step 1: Write failing chart contract tests**

```python
EXPECTED = {
    "01_横向偏移接触力_深度曲线.png",
    "02_倾斜接触力矩_深度曲线.png",
    "03_联合偏差载荷_深度曲线.png",
    "04_穿透量与接触数_深度曲线.png",
    "05_时间步收敛对比.png",
}


def test_generate_v1_charts_writes_five_readable_pngs(tmp_path):
    outputs = generate_v1_charts(TRACE_FIXTURE, CONVERGENCE_FIXTURE, tmp_path)
    assert {path.name for path in outputs} == EXPECTED
    for path in outputs:
        with Image.open(path) as image:
            assert image.width >= 1600
            assert image.height >= 900
            assert "未经实物标定" in image.info["Disclaimer"]
```

- [ ] **Step 2: Run tests and verify missing module failure**

```powershell
& 'D:\KEYANRUJIAN\python.exe' -m pytest tests/visualization/test_v1_contact_plots.py -q
```

- [ ] **Step 3: Implement five focused figures**

Reuse `tools.visualization.font_support.find_chinese_font`. Plot depths in mm, penetration in micrometres, and preserve SI units in labels. Use `0.0002 s` for full-case curves; the convergence figure overlays all three timesteps and includes PASS/FAIL annotations from the convergence JSON. Do not infer missing cases.

- [ ] **Step 4: Reject unsupported schema and missing cases**

Add tests that schema 2 and a trace set without `combined_a` raise `ValueError` with a useful message.

```powershell
& 'D:\KEYANRUJIAN\python.exe' -m pytest tests/visualization/test_v1_contact_plots.py -q
```

Expected: all chart tests pass.

- [ ] **Step 5: Commit chart generation**

```powershell
git add tools/visualization/plot_v1_contact_validation.py tests/visualization/test_v1_contact_plots.py
git commit -m "feat: plot V1 contact validation curves"
```

---

### Task 5: 可追踪技术报告生成器

**Files:**
- Create: `tools/reporting/generate_v1_contact_report.py`
- Create: `tests/reporting/test_v1_contact_report.py`

**Interfaces:**
- Consumes: validated trace and convergence documents plus five chart paths.
- Produces: `build_v1_report(trace_document, convergence_document) -> str`, `write_v1_report(...) -> Path`.

- [ ] **Step 1: Write failing report-content tests**

Require exact section headings and values sourced from fixture JSON:

```python
def test_report_contains_method_gates_failures_and_boundaries():
    report = build_v1_report(trace_document, convergence_document)
    for heading in (
        "## 验证范围", "## 模型与固定配置", "## 工况与深度网格",
        "## 接触曲线证据", "## 时间步收敛", "## 穿透与数值稳定性",
        "## 总体验收", "## 局限性与后续工作",
    ):
        assert heading in report
    assert convergence_document["overall_status"] in report
    assert trace_document["source_contact_results_sha256"] in report
    assert "未经实物标定" in report
```

- [ ] **Step 2: Run tests and verify missing module failure**

```powershell
& 'D:\KEYANRUJIAN\python.exe' -m pytest tests/reporting/test_v1_contact_report.py -q
```

- [ ] **Step 3: Implement deterministic Markdown rendering**

Render tables directly from convergence records; never copy measured values into source constants. Link the five charts by project-relative paths. Write UTF-8 LF and end with one newline.

- [ ] **Step 4: Verify PASS and FAIL documents both render honestly**

Add a fixture with one failed comparison and require the report to show the case, timestep, failed metric, measured value, and frozen limit.

```powershell
& 'D:\KEYANRUJIAN\python.exe' -m pytest tests/reporting/test_v1_contact_report.py -q
```

- [ ] **Step 5: Commit report generation**

```powershell
git add tools/reporting/generate_v1_contact_report.py tests/reporting/test_v1_contact_report.py
git commit -m "feat: generate V1 validation report"
```

---

### Task 6: 一条命令交付、详细使用说明与真实结果

**Files:**
- Modify: `tools/validation/run_v1_contact_validation.py`
- Create: `deliverables/chinese_visual_package/V1接触验证使用说明.md`
- Modify: `deliverables/chinese_visual_package/中文使用说明.md`
- Create: `tests/visualization/test_v1_delivery_package.py`
- Generate: `reports/v1_contact_traces.json`
- Generate: `reports/v1_contact_traces.csv`
- Generate: `reports/v1_timestep_convergence.json`
- Generate: `reports/v1_contact_validation_report.md`
- Generate: `deliverables/chinese_visual_package/charts/v1_contact_validation/*.png`

**Interfaces:**
- Consumes: Tasks 1-5 public functions.
- Produces: `python -m tools.validation.run_v1_contact_validation` one-command delivery.

- [ ] **Step 1: Write failing delivery and entry-point tests**

Require the beginner guide to exist, the existing Chinese guide to link it and the five-chart directory, and these commands copied from the guide to execute successfully:

```powershell
& 'D:\KEYANRUJIAN\python.exe' -m tools.validation.run_v1_contact_validation
& 'D:\KEYANRUJIAN\python.exe' -m tools.reporting.generate_manifest --verify
```

Test that the CLI `--help` lists default output paths and `--check-only` validates existing outputs without rerunning MuJoCo. Do not grep prose headings as a substitute for human documentation review.

- [ ] **Step 2: Run delivery tests and verify failure**

```powershell
& 'D:\KEYANRUJIAN\python.exe' -m pytest tests/visualization/test_v1_delivery_package.py -q
```

Expected: guide and CLI options are missing.

- [ ] **Step 3: Wire the one-command orchestrator**

The default command must:

1. generate 36 traces;
2. validate and atomically write trace JSON/CSV;
3. compute and write convergence JSON;
4. generate five charts;
5. generate the report;
6. print every output path, SHA-256, trace count, sample count, and overall status;
7. exit nonzero only for generation/validation errors, not merely because convergence status is `FAIL`.

`--check-only` reads and validates tracked outputs, checks all hashes it can derive, prints the stored overall status, and performs no model run.

- [ ] **Step 4: Write the detailed beginner guide and update the existing guide**

Write full prose, field dictionaries, chart-by-chart instructions, troubleshooting, scientific boundaries, and a copyable reproduction record template. Avoid references such as "see above" that fail when a section is copied separately.
After writing, manually review the guide against all 12 design-mandated topics, execute every copyable command, open every referenced file path, and check the explanations from a first-time Git/Python user's perspective.

- [ ] **Step 5: Run the real V1 matrix and generate tracked outputs**

```powershell
& 'D:\KEYANRUJIAN\python.exe' -m tools.validation.run_v1_contact_validation
```

Expected: 36 traces, five PNGs, JSON/CSV/report paths, source schema-3 hash, and an explicit `PASS` or `FAIL` without hidden cases.

- [ ] **Step 6: Run delivery tests and check-only validation**

```powershell
& 'D:\KEYANRUJIAN\python.exe' -m pytest tests/visualization/test_v1_delivery_package.py tests/contact/test_v1_contact_outputs.py tests/reporting/test_v1_contact_report.py -q
& 'D:\KEYANRUJIAN\python.exe' -m tools.validation.run_v1_contact_validation --check-only
```

- [ ] **Step 7: Commit the complete V1 delivery**

```powershell
git add tools/validation/run_v1_contact_validation.py deliverables/chinese_visual_package reports/v1_contact_traces.json reports/v1_contact_traces.csv reports/v1_timestep_convergence.json reports/v1_contact_validation_report.md tests/visualization/test_v1_delivery_package.py
git commit -m "feat: deliver complete V1 contact validation"
```

---

### Task 7: 完整性、视觉 QA、回归、manifest 与发布

**Files:**
- Modify: `reports/collision_geometry_report.md`
- Modify: `README.md`
- Modify: `reports/final_file_manifest.txt`

**Interfaces:**
- Consumes: all generated artifacts and test suites.
- Produces: audited feature branch ready for GitHub.

- [ ] **Step 1: Update existing technical entry points without duplicating generated values**

Add concise links from `README.md` and `reports/collision_geometry_report.md` to the new report and beginner guide. State that schema-3 remains the peak-summary baseline and schema-1 trace results are the V1 curve/convergence evidence.

- [ ] **Step 2: Visually inspect all five PNGs at original resolution**

Check Chinese glyphs, titles, axes, legends, line separation, clipping, whitespace, scientific disclaimer, and visible PASS/FAIL status. If any issue exists, fix the generator, rerun the chart tests, regenerate all five images, and inspect again.

- [ ] **Step 3: Run focused suites**

```powershell
& 'D:\KEYANRUJIAN\python.exe' -m pytest tests/contact tests/visualization tests/reporting -q -W error -p no:cacheprovider --basetemp 'C:\Users\OKEVER~1\AppData\Local\Temp\dsub9-v1-focused'
```

Expected: zero failures and zero warnings.

- [ ] **Step 4: Prove protected baselines are unchanged**

```powershell
(Get-FileHash -Algorithm SHA256 -LiteralPath 'reports\contact_validation_results.json').Hash
git diff feature/dsub9-chinese-visual-package -- models assets/collision plugins/dsub9_hole_sdf reports/contact_validation_results.json
```

Expected hash: `AC767EA63A7E8A6866A974728A1256E688832003076170E270CD181E5C9D65FF`; expected diff: empty.

- [ ] **Step 5: Regenerate and verify the reviewed-file manifest**

```powershell
& 'D:\KEYANRUJIAN\python.exe' -m tools.reporting.generate_manifest
& 'D:\KEYANRUJIAN\python.exe' -m tools.reporting.generate_manifest --verify
```

- [ ] **Step 6: Run the full project suite once**

```powershell
& 'D:\KEYANRUJIAN\python.exe' -m pytest -q -W error -p no:cacheprovider --basetemp 'C:\Users\OKEVER~1\AppData\Local\Temp\dsub9-v1-final'
```

Expected: all tests pass with no skips or warnings. Run with normal Windows SDK permissions if the restricted process cannot access Microsoft SDK metadata.

- [ ] **Step 7: Perform a concentrated local review**

Review schema compatibility, zero-reference math, common-depth alignment, threshold enforcement, error paths, documentation accuracy, generated-vs-source value consistency, and `git diff --check`. Fix findings through focused tests before continuing.

- [ ] **Step 8: Commit final documentation and manifest**

```powershell
git add README.md reports/collision_geometry_report.md reports/final_file_manifest.txt
git commit -m "docs: publish V1 contact validation evidence"
```

- [ ] **Step 9: Push only the feature branch and verify the remote ref**

```powershell
git push -u origin feature/dsub9-v1-contact-validation
git ls-remote --heads origin feature/dsub9-v1-contact-validation
```

Do not merge or force-push. Preserve the isolated worktree for follow-up review.
