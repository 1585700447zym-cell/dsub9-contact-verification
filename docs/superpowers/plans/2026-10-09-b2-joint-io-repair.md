# B2-SCOPE-14 文件并发修复与恢复证据计划

> 使用 superpowers:executing-plans 在现有工作区执行；用户已要求继续已明确的离线修复。保留所有未提交修改和历史封存，不提交、不新建工作区。

**Goal:** 修复导致 SCOPE13 中断的读写访问竞争，并明确可重建的预热状态及尚待数值验证的部分。

**Architecture:** 在新阶段目录形成 joint_contract/supervised 的最小修复候选，以 bounded_io 提供限定时长的瞬态重试。监督器持续执行整体和最近有效阶段的绝对截止时间；只用标准库、已有 JSON/gzip 档案做恢复来源核对。

**Tech Stack:** Windows、Python 标准库、unittest；不导入 NumPy、Torch、MuJoCo，不加载张量或创建物理环境。

**Spec:** `deliverables/learning_chain/b2_joint_sac_execution_20261009/失败原因与修复路线.md`

## Global Constraints

- 旧 SCOPE12/SCOPE13 及其授权、计数、模型和档案不变；累计动态245，正式更新新增0，自动跟踪PAUSED。
- 研究范围、共同配置、保护、奖励、SAC数值算法不变。
- 文件重试最多0.5秒，且不得越过外部传入的绝对 monotonic 截止；保留失败暂存数据。
- 只对Windows瞬态 PermissionError（winerror 5/32/33，或 errno13 且无winerror）重试；其他异常立即交给原关闭路径。
- 全项目仿真/学习测试不在本次授权内；执行完整新文件/监督器离线测试集和受影响旧纯检查。

## Review Focus

- 临时锁解除后的真实读取和替换必须成功，持续锁不能无限等待。
- 截止前最后一次文件调用结束后也要检查期限，不能以读到新记录重置旧期限。
- 损坏JSON、非有限时间、未知阶段类型不得逃过监督。
- 正常退出、错误退出和截止退出都必须确认拥有的子进程树退出。
- 缺失/重复/篡改预热档案不能形成可继续结论；未核验的随机状态不能写成恢复通过。

## Task 1 — bounded_io 与原接口修复

Files: 新阶段目录的 `bounded_io.py`、`joint_contract.py`、`test_io_repair.py`。

Interface: `read(path, *, deadline=None)`、`write(path,value, *, deadline=None)`；deadline是monotonic绝对时刻。旧无关键字调用保持可用。

- [x] 真实Windows独占锁下先运行原read/write的恢复测试，记录预期失败。
- [x] 加入读/替换瞬态重试，限定单操作0.5秒；暂存只写一次，不能重试物理或学习操作。
- [x] 验证短锁、永久锁、损坏JSON、非权限错误和文件并发完整读取。

## Task 2 — supervisor 截止及进程回归

Files: `phase_deadline.py`、`supervised.py`、`test_supervisor.py`、`fixture_worker.py`。

Interface: `PhaseDeadline(whole_deadline).check()`、`.read_phase(path)`；读取受当前最早截止约束。

- [x] 测试新记录不能救回已超时旧阶段、重复读不能延长截止、墙钟变化不能延长已记住的期限。
- [x] 以真实标准库子进程测试正常退出、错误退出、锁/阶段/整体超时和拥有进程树退出。

## Task 3 — 恢复来源核对

Files: `recovery_audit.py`、`test_recovery_audit.py`、`recovery_assessment.json`。

Interface: `inspect_warmup(raw,receipt,expected_id,draws)` 返回控制行数、活动行数、累计抽样数、末次held和边界摘要；不发布经验。

- [x] 先写错误序列、抽样保持、截断/缺失终末及receipt冲突的反例，再实现核对。
- [x] 读取四份已有预热档案，核对完整顺序、策略hash、原资格hash、回放内容和50周期动作保持；记录可重建依据。
- [x] 按网络/优化器/回放/三个NumPy RNG/策略Torch RNG分别说明已证与待证；不把来源完备当实际数值恢复通过。

## Task 4 — 复核与交付

- [x] 新旧相关纯测试完成；独立代码审查并处理实质问题。
- [x] 原封存哈希、绑定输入、分支、未提交文件保留验证。
- [x] 更新五份滚动文档并保存六份快照；结果、恢复路线、测试日志及新候选封存。
- [x] 本阶段报告完成状态与下一项，不启动旧试跑或未准备的新训练。
