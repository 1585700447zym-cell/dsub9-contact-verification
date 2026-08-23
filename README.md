# D-sub9 精密插接碰撞几何

本仓库交付 D-sub9 公母头的对齐视觉网格、CAD 截面导向壁、9 组针—孔碰撞表示、
MuJoCo 3.x 解析 SDF 插件和准静态接触验证。正式模型是 `models/dsub9_pair.xml`，其母孔使用
9 个解析圆孔 SDF；`polygon32` 仅是性能/稳定性对照回退，不是正式模型。

这是几何与数值接触基线。它没有控制器、机器人或强化学习环境，也没有标定真实插入力；报告中的
N/N·m 只是未标定的模型诊断值，不得用作实物安全阈值。

## 环境

- Windows x64，Python `>=3.11`。
- 本机已验证 `D:\KEYANRUJIAN\python.exe` （Python 3.13.5）。`$projectPython` 只是可配置变量；
  在新环境中把它改为实际 Python 3.11+ 路径。
- 构建 SDF 插件需要 CMake、Visual Studio 2026 C++ x64 工具集和 Windows SDK。已验证的生成器是
  `Visual Studio 18 2026`。
- 下面命令均从项目根目录执行。PowerShell 参数使用引号或 `Join-Path`，可处理 D 盘、
  中文及空格路径。

```powershell
$projectRoot = 'D:\dsub9项目计划\first_stage_sim'
$projectPython = 'D:\KEYANRUJIAN\python.exe'
Set-Location -LiteralPath $projectRoot

& $projectPython --version
& $projectPython -m pip install -e '.[test]'
```

`pip install` 可能根据本地缓存/包源安装 NumPy、pytest 和 MuJoCo；本仓库的最终审计没有联网执行该步。

## 视觉资产

母头 STL 可由受控工具重建：

```powershell
& $projectPython -m tools.mesh.normalize_visual_meshes --female
```

这一步对原始母头 STL 只平移 `[-15.4, -6.275, 0] mm`，不缩放、不旋转，并重算面法向。

公头 STL 不能由本仓库全自动从 STEP 重导出。仓库已跟踪并审阅
`assets/visual/dsub9_male_visual_centered.stl`，一般复现可直接使用它。若必须重导，需在 SOLIDWORKS 中对
`DSub9_Deliverables_V4/DSub9_Male_TwoStageRearShell_V3.step` 手工使用如下设置：

- SOLIDWORKS Premium 2023 SP5.0，构建 `31.5.0.0052`；
- 二进制 STL，单位 mm，自定义分辨率；
- 最大弦偏差 `0.01 mm`，最大角度公差 `5°`；
- 坐标系使用默认，勾选“不要转换 STL 输出数据到正坐标空间”，不做手动变换。

导出后必须验证尺寸和原点：

```powershell
$maleVisual = Join-Path $projectRoot 'assets\visual\dsub9_male_visual_centered.stl'
& $projectPython -m tools.mesh.normalize_visual_meshes --validate-male $maleVisual
```

完整手工设置和已审阅包围盒见 `reports/solidworks_export_settings.md`。

## 碰撞资产、插件与模型

重生成 78 个公头 D 导向块、42 个母头 D 插座块和 576 个 `polygon32` 回退扇区：

```powershell
& $projectPython -m tools.mesh.generate_collision_assets
```

配置并构建 Release SDF 插件：

```powershell
$mujocoRoot = & $projectPython -c "import pathlib,mujoco; print(pathlib.Path(mujoco.__file__).resolve().parent)"
$pluginSource = Join-Path $projectRoot 'plugins\dsub9_hole_sdf'
$pluginBuild = Join-Path $projectRoot 'build\dsub9_hole_sdf'
cmake -S $pluginSource -B $pluginBuild -G 'Visual Studio 18 2026' -A x64 "-DMUJOCO_ROOT=$mujocoRoot"
cmake --build $pluginBuild --config Release
```

在已验证的 MuJoCo 3.9.0/Windows 上，工作区的中文绝对 DLL 路径曾出现“调用返回但插件未注册”。
请始终从项目根目录启动，让 MuJoCo 加载 ASCII 项目相对路径
`build/dsub9_hole_sdf/Release/dsub9_hole_sdf.dll`；不要把本观察外推到未测试的 MuJoCo 版本。

生成正式 SDF 模型和仅供对照的 `polygon32` 回退模型：

```powershell
& $projectPython -m tools.model.generate_mjcf --collision-mode sdf --output 'models/dsub9_pair.xml'
& $projectPython -m tools.model.generate_mjcf --collision-mode polygon32 --output 'build/dsub9_pair_polygon32.xml'
```

## 测试、接触结果与清单

```powershell
& $projectPython -m pytest -v -W error
& $projectPython -m tools.validation.run_contact_cases --all --output 'reports/contact_validation_results.json'
& $projectPython -m tools.reporting.generate_manifest
& $projectPython -m tools.reporting.generate_manifest --verify
```

接触 runner 运行 16 个真实场景，直接指定位姿并调用 `mj_forward`。它不是自由动力学积分，没有力控制器，
也不会产生可观测的 stalled-progress 状态。判定只有 `SUCCESS`、`EXCESS_PENETRATION` 和
`NUMERICAL_ERROR`。当前 30 µm 穿透阈值是 75 µm 名义径向间隙的 40%，而不是力阈值。

`reports/final_file_manifest.txt` 覆盖 `assets/`、`models/`、`plugins/`、`tools/`、`tests/`、
`reports/` 下的受审文件，以及根目录的 README、`pyproject.toml` 和 `.gitignore`。每行使用小写
SHA-256 和按 POSIX 相对路径排序。为避免自引用哈希无限变化，清单必须且仅对
`reports/final_file_manifest.txt` 自身例外；`--verify` 会重算全部其他条目并拒绝陈旧清单。`build/`不纳入清单，
Release DLL 的已测试 SHA-256 记录在 `reports/collision_geometry_report.md`。

## 执行环境限制

受限 Codex runner 曾在 MSBuild 检查用户级 Windows SDK 元数据时返回 `MSB4184`/访问被拒绝；同一源码和
命令在正常 Windows 本机终端中已完成 x64 Release 构建和零 skip 全量测试。这是权限隔离差异，不是
插件源码失败。普通用户应在具有 Visual Studio/Windows SDK 访问权的本机 PowerShell 中直接执行上述
构建和测试命令；不需要、也不应复制任何临时 pytest 注入器。
