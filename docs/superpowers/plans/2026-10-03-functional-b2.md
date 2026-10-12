# 功能插入与共同B2倾斜风险卸载实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. 保留全部未提交成果，不新建工作树、不提交、不清理。

**Goal:** 分开功能成功与附加精度，并验证一次最小共同B2修复能否消除已见入口倾斜故障。

**Architecture:** 原会话增加两个默认等价的观察/完成判据方法；独立功能会话复用原生命周期、保护和物理尾段。新B2子类只增加持续高载荷/相对旋转触发UNLOAD，继承原搜索、恢复和预算。

**Tech Stack:** 当前Python、限定MuJoCo 3.13、NumPy、pytest。

**Spec:** 当前研究计划2026-10-03修订、clearance120_20261003/诊断与下一步.md及用户“继续”的执行授权。

## Global Constraints

- 使用既有工作树/分支，快照本次原源码；旧210文件封存逐项校验。自动跟踪PAUSED。
- 几何沿用1.20 mm孔/1.00 mm针。主成功：目标深度20 μm、九针全轴保守孔内配合、原速度/载荷/穿透限制和0.1 s连续保持、全回合保护优先、实际停稳。80 μm/0.5°作为额外精度结果独立报告，不追改旧结果。只表示当前刚性几何插入，不表示真实电接触。
- 新共同控制规则仅用初始相对位移、相对旋转和六维力，不输入孔中心/配合判据。INSERT中相对转角≥1.5°且轴向压载≥15 mN持续0.05 s触发UNLOAD；2.5°保护线不变。旧±X150在原卸载前不到1.5°，预计不影响原轨迹，需实际复验。
- 最多9个新纯B2开发回合，累计117→上限126；固定顺序正Y150、负Y150、正X150、负X150、对准、正X100、负X100、正Y100、负Y100。旧余1关闭，无重试。网络推理0、更新0、独立测试0。
- 第一回合若仍非FULL_SUCCESS即停止，避免继续消耗；后续普通有效失败可继续；任何保护、无效仿真、初始化/运行故障或未停稳立即封闭余量。每个尝试先写账，归档完整轨迹/控制事件/保护/尾段，500周期进度，1200 s/回合墙钟上限。停止不表示修复通过。
- 不追加参数搜索；若失败，交付失败原因和下一步判断。若通过也只获得共同任务基线证据，不等于B.2完成或批准训练。

## Review Focus

- 原默认会话保持50 μm/0.5°，新功能判据不能漏掉深度、九针几何、速度、保护及连续保持。
- 相对姿态不能使用孔位真值；缺失/非有限输入不得触发或悄悄运行；风险持续时钟应在条件解除或离开INSERT时复位。
- 搜索次数耗尽仍失败，旧低载荷退出与恢复保护不能被新分支绕过。
- 中断/磁盘写入故障保留小账和已有原始轨迹，错误回合不重试，不漏计。
- 汇报分别显示功能/精度与控制器效果，不把重新定义成功的收益归给控制改进。

## Task 1: 功能会话与风险触发

**Files:** 修改tools/learning/session.py的两处方法提取；新增tools/model/functional_task.py、tools/control/risk_search.py、tools/learning/functional_session.py、tests/task_variants/test_functional_b2.py。

**Interfaces:** EpisodeSession.policy_observation(row)、completion_ready(row)保持默认；functional_finish(row,criteria)->bool；PoseObservation追加relative_rotation_rad；RiskSearchRecovery(config,risk_config)；FunctionalCandidateSession复用CandidateEpisodeSession。

- [x] 写功能/严格精度分离、错误深度/倾斜/运动反例、保持被打断、风险持续/解除/搜索预算测试，运行看到缺失实现失败。
- [x] 实现并跑相关新旧检查；离线重放旧Y150与X150观察，核对新触发原因和时间，不推断动态结果。

## Task 2: 有限验证入口

**Files:** tools/validation/run_functional_preflight.py及tests/task_variants/test_functional_preflight.py，交付目录deliverables/task_variants/functional_b2_20261003。

**Interfaces:** 复用已测原子账/错误档案工具；新增固定预算、首例门槛、独立路径和源码绑定；继承原prepare/execute结构但不修改旧runner。

- [x] 先写并运行停止/预算测试，再实现入口；一次独立只读审查并修复重要发现。
- [x] 静态准备/快照/锁定输入，然后按上限实际执行；任何关闭余量不结转。

## Task 3: 结论与交付

- [x] 复核所有落盘档案，分别报告功能、严格精度、载荷、时长、风险事件和停稳；比较旧同工况但明确任务判据不同。
- [x] 更新当前计划、入口、进度（含能力/原八项/风险/追加日志）、总览和10月滚动月报，保存快照并封存新结果。

## 执行裁定

用户已有“调整后直接推进”和本轮继续授权，按此计划直接执行。使用交付目录progress.md作为持久账，替代依赖提交的bash工作区脚本；相关检查不隐式启动历史长动态/旧运行库全套测试。审查在本轮真实动态前进行，确认新代码和共同规则后再消费物理预算。

## 实际收口（2026-10-04）

实施和有限验证按规则完成，性能整体未通过：65项相关检查通过；2/9动态，正Y功能成功、负Y总力保护，余7关闭，累计119。完整判据复核、两图、失败诊断、四份滚动资料与封存已整理。执行时未勾选的计划在source_snapshot中保留；此处勾选不表示B.2、完整9点或学习准入通过。
