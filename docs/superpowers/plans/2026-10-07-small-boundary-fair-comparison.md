# 公平小边界对照后续实现计划（未执行）

> For agentic workers: 后续经用户确认实施范围后用superpowers:executing-plans inline。此文件是待执行计划，步骤均未开始；本阶段只交付草案。沿用原工作区，不提交、不清理、不启动旧runner。

**Goal:** 复用现有数值引擎，实现F12.5真实物理尺度、归一化回放及完整外层检查点，并在新资格/预算后执行一次有限比较。

**Architecture:** 独立新执行目录中的物理profile会话、整回合审计与检查点外层，调用不变的原SAC/回放/恢复核心。保持共享1057输入与共同key，旧F/S/B2原档案只作为历史评价证据；任何无法保持的核心变化使继承方案停止。

**Tech Stack:** 现有Python/NumPy/CPU torch/SB3/MuJoCo3.13，不增依赖、维数或学习模块。

**Spec:** [登记设计](../specs/2026-10-07-small-boundary-fair-comparison-design.md)，[机器草案](../../../deliverables/paper_comparison/small_boundary_registration_20261007/draft_contract.json)。

## Global Constraints

- 当前无训练/数值计算/物理授权，自动跟踪PAUSED、累计208；本计划本身不是资格。
- 原1057共享输入、common_key `199f0f49c535cb6d941c21344f5c81976e949bb444611bd9eddaab35f66527b5`保持。新执行目录拟为`deliverables/paper_comparison/small_boundary_execution_20261007`，尚未创建。
- 外层profile=F12p5，物理尺度[12.5e-6,12.5e-6,0.000125,0.000125]；内部数值引擎mode=F50须明确独立身份，资格SHA唯一绑定外层。
- 回放使用未缩放归一化a，物理请求才缩放；禁止旧F/S权重或数据进入新训练，不把旧档案改标签。
- 拟21动态/2000正式批＋单列4合成更新/32测试状态；具体执行上限以将来新授权、资格和一次性账本交集为准。

## Review Focus

- 错尺度/错profile或裸旧检查点必须在任何恢复/推理之前拒绝。
- a与0.25a在warmup、随机在线、确定性策略和critic路径一致；停止/恢复始终0经验动作。
- 只读观察不能多推进基线；保存恢复必须重审原始物理请求，不只信内部F50标签。
- 发布前校验外层资格；有效普通失败保留，保护后不获得额外更新信用。
- 继承门失效、预算不足或矩阵缺失停止；不自动三组重训、不事后选最优检查点。

## Task 1：真实小尺度与外层审计（未开始）

Create: 新执行目录`small_bound_profile.py`、`test_small_bound_profile.py`。

Interfaces: `SmallBoundSession(ContinuationResidualSession)`保持生命周期，仅物理合成采用0.25a；`audit_small_bound_episode(raw,contract)`同时核对原始a、内部compositor_action、实际物理请求、掩码、奖励与执行命令；`validate_outer_contract(contract)`仅接受完整注册profile。

- [ ] 手算反例RED：四轴±1对应固定尺度；保存a与0.25a分列；恢复/保护/切换屏蔽；错尺度/漏profile拒绝。
- [ ] 最小实现及GREEN；对现有已存循环状态做纯命令级等价反算，零残差全部对应旧B2、50内部映射不改变任何共享源码。
- [ ] 来源不变及动作语义审查；若必须改共同源，停止继承方案并记录影响，不继续本计划。

## Task 2：数值引擎与完整外层检查点（未开始）

Create: 新执行目录`small_bound_learning.py`、`test_small_bound_checkpoint.py`。

Interfaces: `SmallBoundChain`组合原`V4Chain`，在begin/finish/update/save前复核外层profile；`save_small_bound_checkpoint(chain,path)`与`read_small_bound_checkpoint(path,expected_profile_digest)`外层包含物理合同及完整内部检查点，先外层再内部审核。

- [ ] 纯数据/协议反例RED：F50/S50旧裸检查点、profile缺失/改尺度、归一化动作错用、入池前资格变化、保护后更新拒绝。
- [ ] 最小外层GREEN，不复制SAC或放宽原数值恢复；新0更新起点和空回放元数据须与旧记录匹配。
- [ ] 提交独立数值门清单（最多4合成事务、32测试状态），当前不执行；获明确该计算授权后再验证完整落盘/新进程恢复及采样索引、优化器、RNG。

## Task 3：一次性驱动与执行资格（未开始）

Create: 新执行目录`run_small_bound_pilot.py`、`test_small_bound_budget.py`、`qualification_candidate.json`。不创建已准入资格文件。

Interfaces: `attempt_specs(contract)`固定21次次序；`reserve_task(kind,remaining_wall_s)`先预留单次硬上限；`verify_admission()`必须同时检查新执行授权、准入、来源与外层尺度绑定。

- [ ] 反例RED：缺授权/准入、超额度、越过保护、额外预热、旧余量、重复领取、时间不足启动、评价入池、挑中间检查点全部拒绝。
- [ ] 实现纯协议GREEN及限定独立审查；冻结新代码/模型/runtime和旧继承评价SHA。
- [ ] 先形成可审阅执行候选，再请求新预算授权；未经授权不运行--execute，不恢复自动跟踪。

## Task 4：一次执行、证据收口与决策（未开始）

Create: 新执行目录的账本、档案、成本、结果与封存；Modify: 根进度/总览/入口/当前计划/当月月报，保存快照。

- [ ] 获授权后先2物理预检，通过后核对训练资格；按5初始、4预热、4在线、5最终、1复现执行，实际计数持久化。
- [ ] 逐条原始审核功能/精度/停稳/奖励/掩码/参考与来源；所有失败、缺失及关闭余额如实保存。
- [ ] 按设计继续门及路线表作决定，旧S/F负结果保持。文档更新、冻结收口后暂停汇报；B.2/C与论文D另行登记。

## 本次自审

动作/数据/检查点/预算接口已命名并相互一致；预算与机器草案对应。没有TBD、自动复跑或已准入标志。拟实现文件与现有engine身份隔离属于需验证设计，未冒称已实现；后续实现发现兼容问题必须停止此继承方案。
