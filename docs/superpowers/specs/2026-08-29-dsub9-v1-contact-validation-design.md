# D-sub9 V1 接触验证补齐设计

## 1. 目标

在不修改已验收的 D-sub9 几何、接触参数和 schema-3 峰值结果的前提下，把现有“准静态姿态扫描摘要”扩展为可验收的 V1 接触验证交付：

- 保存逐深度六维接触轨迹；
- 生成理想、横向、倾斜和联合误差接触曲线；
- 在固定深度网格上隔离求解器时间步影响；
- 对数值有限性、终止、主要载荷方向、穿透与曲线收敛给出机器可检查的判定；
- 交付中文图表、平面 CSV、结构化 JSON 和独立 V1 报告。

## 2. 范围与科学边界

本任务仅补齐 Model V1 的准静态接触验证，不引入：

- V2 pin/socket 等效柔顺；
- Fixed 或 Search/Adaptive Admittance 控制器；
- Failure Boundary 概率网格；
- 机器人、F/T 传感器、Residual SAC、Risk Supervisor 或 Hard Safety Guard；
- 实物插入力标定。

全部载荷继续标注为未经实物标定的数值诊断。轨迹由规定姿态和 `mj_forward` 产生，不是自由动力学插入或控制器轨迹。

## 3. 方案选择

### 3.1 采用：新增独立 trace schema

保留 `reports/contact_validation_results.json` 的 schema-3 和 SHA-256 不变，新建 V1 trace schema-1。旧消费者继续读取旧文件，新图表和报告仅读取新文件。

优点是不破坏已验收基线、可单独重生成、便于将来和 V2 结果并行管理。

### 3.2 不采用：把 trace 嵌入 schema-3

将 schema-3 升级为 schema-4 虽然只有一个 JSON，但会改变已跟踪哈希、现有图表消费者和交付说明，风险不必要。

### 3.3 不采用：只交付图片而不交付轨迹

只有图片无法复核采样网格、重算收敛指标或用于后续回归，不满足可追踪性。

## 4. 运行时架构

### 4.1 共享扫描内核

`tools/validation/run_contact_cases.py` 中将现有扫描循环抽取为一个共享内核。它一次运行同时产生：

- 既有 `ContactResult` 峰值摘要；
- 可选的 `ContactSample` 逐深度样本。

现有 `run_case(...) -> ContactResult` 的签名、默认空间步长行为和数值结果保持不变。新接口为：

```python
def run_case_trace(
    case: ContactCase,
    timestep_s: float,
    collision_mode: CollisionMode,
    *,
    profile: str = "baseline",
    spatial_step_m: float = 0.00001,
) -> ContactTrace:
    ...
```

### 4.2 轨迹数据类型

`ContactSample` 为冻结 dataclass，字段固定为：

- `step_index: int`
- `depth_m: float`
- `male_origin_z_m: float`
- `wrench: Wrench`
- `force_norm_n: float`
- `torque_norm_nm: float`
- `contact_count: int`
- `penetration_m: float`

`ContactTrace` 包含：

- `case: ContactCase`
- `collision_mode: str`
- `contact_profile: str`
- `timestep_s: float`
- `spatial_step_m: float`
- `solver: str`
- `samples: tuple[ContactSample, ...]`
- `summary: ContactResult`

所有浮点必须有限，深度单调不减，最后样本和摘要终止深度一致。

### 4.3 V1 矩阵

生成器使用正式 SDF 模型和 baseline 接触配置，执行 `all_cases()` 的 12 个已冻结工况。`separated` 作为零接触卫生检查；其余 11 个插入工况进入曲线和收敛评估。

求解器时间步为：

- `0.0004 s`；
- `0.0002 s`；
- `0.0001 s`（精细参考）。

三组运行都使用独立于时间步的 `0.00001 m` 固定深度增量。因此同一工况的每个比较点都对应同一规定姿态。

## 5. 文件与 schema

### 5.1 结构化 JSON

`reports/v1_contact_traces.json` 使用 `schema_version: 1`，包含：

- 坐标系、单位和未标定声明；
- 固定深度网格和三个时间步；
- 12 个工况的定义；
- 36 条轨迹及其摘要；
- 源 schema-3 JSON 的 SHA-256；
- 可达的终止枚举。

JSON 使用 UTF-8、LF、排序键与 `allow_nan=False`。

### 5.2 平面 CSV

`reports/v1_contact_traces.csv` 每行一个样本，保留工况、时间步、空间步长、六维 wrench、合力、合力矩、接触数和穿透量。文件使用 UTF-8 with BOM，便于中文 Windows Excel 直接打开。

### 5.3 收敛摘要

`reports/v1_timestep_convergence.json` 使用 `0.0001 s` 作为参考，对每个插入工况计算：

- 终止是否一致；
- 是否出现 `NUMERICAL_ERROR`；
- 主要有符号 wrench 分量的方向是否一致；
- 终止深度差；
- 最大穿透量差；
- 峰值合力和合力矩相对差；
- 主要 wrench 分量在公共深度区间的归一化 RMSE。

当参考曲线的峰值为零时，相对差和归一化 RMSE 记为 `null`，并使用 `1e-12` 的绝对零接触卫生门槛。不用人工 epsilon 把零值伪装成有意义的相对误差。

## 6. 验收规则

规则在生成正式结果前固定：

### 6.1 硬门槛

- 36 条轨迹全部为有限数；
- 全部轨迹不得以 `NUMERICAL_ERROR` 终止；
- 同一工况三个时间步的终止枚举一致；
- 带方向判据的横向、倾斜和联合工况主要分量符号一致；
- 与 `0.0001 s` 参考相比，终止深度差不大于 `0.00001 m`；
- `separated` 和 `aligned` 的零接触载荷范数不大于 `1e-12`。

### 6.2 收敛目标

对存在非零接触的工况：

- `0.0002 s` 相对 `0.0001 s`：峰值合力、峰值合力矩和主要分量归一化 RMSE 目标均不超过 `10%`；
- `0.0004 s` 相对 `0.0001 s`：对应目标均不超过 `20%`。

任一目标超限时，生成器仍必须保留原始结果并成功写出报告，但总体验收状态必须为 `FAIL`。不得通过改阈值、删工况或修改接触参数使结果变为通过。

## 7. 图表与报告

`deliverables/chinese_visual_package/charts/v1_contact_validation/` 生成五张中文 PNG：

1. `01_横向偏移接触力_深度曲线.png`；
2. `02_倾斜接触力矩_深度曲线.png`；
3. `03_联合偏差载荷_深度曲线.png`；
4. `04_穿透量与接触数_深度曲线.png`；
5. `05_时间步收敛对比.png`。

图表默认以 `0.0002 s` 展示全工况，时间步对比图同时展示三个时间步。每张图在图内和 PNG metadata 中都包含“未经实物标定”声明。

`reports/v1_contact_validation_report.md` 包含：

- 范围、方法和非动力学边界；
- 模型、插件、接触参数和源结果哈希；
- 工况矩阵与固定深度网格；
- 各类接触曲线的可追踪表格；
- 时间步收敛表、超限项和总体 `PASS/FAIL`；
- 穿透、数值发散和终止检查；
- 已完成、未完成与后续 V2/Failure Boundary 接口。

中文使用说明增加 V1 数据、图表和报告的入口，但不把新轨迹称为 RL 时序数据。

## 8. 错误处理

- 非法时间步或空间步长在运行前抛出 `ValueError`；
- 模型、DLL 或输入 JSON 缺失时使用带绝对路径的异常；
- 样本中出现非有限数时，轨迹摘要标记 `NUMERICAL_ERROR`，不写入 NaN/Infinity；
- 生成临时文件后再原子替换正式 JSON/CSV，避免中途失败留下半个文件；
- 图表不支持的 schema 必须明确拒绝，不猜测字段。

## 9. 测试策略

按 TDD 实施，分层测试：

1. 轨迹数据类型、序列化、深度单调性与摘要一致性；
2. 显式空间步长与时间步解耦；
3. 旧 `run_case` 与新共享内核在旧配置下字段级一致（排除 `runtime_s`）；
4. 收敛指标使用人工小轨迹的单元测试，包括零参考值；
5. 真实 SDF 小矩阵验证三个时间步的公共深度网格；
6. JSON/CSV 的编码、字段、顺序和有限数；
7. 五张图的文件名、分辨率、中文字体、声明和可读性；
8. 报告的必要章节、数值与源 JSON 一致；
9. 现有 contact、visualization、reporting 测试全部回归；
10. 项目全量 pytest 通过，最终 manifest 重生成后 `--verify` 通过。

图表生成后必须人工逐张视觉检查，包括中文字形、图例、坐标轴、线条重叠、截断和声明。

## 10. 不变量与验收交付

实施完成后必须证明：

- `models/`、`assets/collision/`、`plugins/dsub9_hole_sdf/` 与基线分支无差异；
- `reports/contact_validation_results.json` SHA-256 仍为 `ac767ea63a7e8a6866a974728a1256e688832003076170e270cd181e5c9d65ff`；
- 既有 schema-3 中的 20 条结果不变；
- 新生成器可用一条命令重生成 JSON、CSV、收敛摘要、五张图和报告；
- 跟踪文件清单及 SHA-256 manifest 是当前状态。

功能在 `feature/dsub9-v1-contact-validation` 分支实现并上传，不自动合并到 `main` 或已发布的中文可视化分支。
