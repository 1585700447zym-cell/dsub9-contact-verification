# D-sub9 精密插接碰撞几何

> **当前使用入口（2026-09-17）：[报告总索引](报告总索引.md) · [项目复现与使用说明](项目复现与使用说明.md) · [256 段模型说明](deliverables/model_exports_256/模型说明.md)。**
>
> 工程现已新增简化动态执行器和 B1 固定导纳开发基线。以下正文保留几何与 V1 阶段的原用法，其中“正式模型”“没有控制器”等描述限定于当时阶段；当前 B1 使用独立的 256 段凸分块孔模型和 MPR 后端。原解析 SDF 场景与代码仍保留。B1 仍有接触工况未完成插入，详见最新开发报告。

本仓库交付 D-sub9 公母头的对齐视觉网格、CAD 截面导向壁、9 组针—孔碰撞表示、
MuJoCo 3.x 解析 SDF 插件和准静态接触验证。正式模型是 `models/dsub9_pair.xml`，其母孔使用
9 个解析圆孔 SDF；`polygon32` 仅是性能/稳定性对照回退，不是正式模型。

这是几何与数值接触基线。它没有控制器、机器人或强化学习环境，也没有标定真实插入力；报告中的
N/N·m 只是未标定的模型诊断值，不得用作实物安全阈值。

碰撞 geom 显式冻结版本化基线 `uncalibrated_diagnostic_v1`：friction `(1, 0.005, 0.0001)`、
`solref=(0.02, 1)`、`solimp=(0.9, 0.95, 0.001, 0.5, 2)` 与零 margin。低/高响应配置
`uncalibrated_low_response_v1`、`uncalibrated_high_response_v1` 仅用于数值敏感性包络，不是材料或
插入力标定。

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

`pip install` 可能根据本地缓存/包源安装 NumPy、pytest、MuJoCo，以及 Windows 上 ACL 测试所需的
pywin32；本仓库的最终审计没有联网执行该步。

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

该命令在 staging 目录中完整生成并校验清单后才事务性替换 `assets/collision/`；若生成、库存校验或
Windows DACL 归一化/后置读取权限校验失败，既有目录保持不变。已对 696 个 collision 文件验证实际
重生成后名称和 SHA-256 不变，并完成 696/696 次普通读取。

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
& $projectPython -m tools.validation.run_v1_contact_validation
& $projectPython -m tools.validation.run_v1_contact_validation --check-only
& $projectPython -m tools.reporting.generate_manifest
& $projectPython -m tools.reporting.generate_manifest --verify
```

接触 runner 直接指定位姿并调用 `mj_forward`，不是自由动力学积分，也没有力控制器。追踪的 schema-3
结果共有 20 条：16 条 `uncalibrated_diagnostic_v1` 基线结果，加上 X +100 µm 与 combined A 两个
SDF 场景各一条 `uncalibrated_low_response_v1` 和 `uncalibrated_high_response_v1` 结果。它不会产生
可观测的 stalled-progress 状态；判定只有 `SUCCESS`、`EXCESS_PENETRATION` 和 `NUMERICAL_ERROR`。
当前 30 µm 穿透阈值是 75 µm 名义径向间隙的 40%，而不是力阈值。

完整 V1 接触验证使用独立的 schema-1，不修改上述 schema-3 基线。它保存 12 个工况、三个时间步和
固定 10 µm 深度网格的逐点六维轨迹，并生成 CSV、收敛判定、五张中文图和技术报告。详细入口：

- [V1 接触验证技术报告](reports/v1_contact_validation_report.md)
- [V1 接触验证详细使用说明](deliverables/chinese_visual_package/V1接触验证使用说明.md)
- [V1 时间步收敛结构化结果](reports/v1_timestep_convergence.json)

V1 的 `PASS` 只表示冻结的数值有限性、方向、终止一致性和收敛门槛通过；它不表示所有偏差工况都成功
插到底，也不表示实物装配、控制器或自由动力学验证通过。逐工况终止原因和所有实测值以 schema-1 JSON
及自动生成报告为准。

`reports/final_file_manifest.txt` 覆盖 `assets/`、`models/`、`plugins/`、`tools/`、`tests/`、
`reports/` 下的受审文件，以及根目录的 README、`pyproject.toml`、`.gitattributes` 和
`.gitignore`。每行使用小写
SHA-256 和按 POSIX 相对路径排序。为避免自引用哈希无限变化，清单必须且仅对
`reports/final_file_manifest.txt` 自身例外；`--verify` 会重算全部其他条目并拒绝陈旧清单。`build/`不纳入清单，
Release DLL 的已测试 SHA-256 记录在 `reports/collision_geometry_report.md`。

根目录 `.gitattributes` 通过 `* text=auto eol=lf` 固定受审文本的 LF 字节，并用 `*.stl binary`
明确禁止 Git 改写 STL。这是使 SHA-256 清单在 `core.autocrlf=true` 的 Windows fresh checkout 中仍可
按原始字节复现的前提。原始 STEP 另以 `text eol=crlf` 锁定已审核的源哈希，SLDPRT 作为
binary 保持原始字节；不要在不重生成并复验 manifest 的情况下删除或弱化这些规则。

## 执行环境限制

受限 Codex runner 曾在 MSBuild 检查用户级 Windows SDK 元数据时返回 `MSB4184`/访问被拒绝；同一源码和
命令在正常 Windows 本机终端中已完成 x64 Release 构建和零 skip 全量测试。这是权限隔离差异，不是
插件源码失败。普通用户应在具有 Visual Studio/Windows SDK 访问权的本机 PowerShell 中直接执行上述
构建和测试命令；不需要、也不应复制任何临时 pytest 注入器。
