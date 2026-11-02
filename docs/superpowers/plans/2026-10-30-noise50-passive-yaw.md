# 50毫秒探索与被动yaw最小对照 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现25周期探索噪声保持，并以四次零更新原生对照判断被动yaw影响。
**Architecture:** 新增隔离噪声模块和独立诊断入口，复用既有collector/runtime/完整审核。旧冻结代码及档案不改，F4000只读使用，无经验发布或优化。
**Tech Stack:** Python/NumPy、冻结SB3 SAC、原MuJoCo3.13 N2。
**Spec:** ../specs/2026-10-30-noise50-passive-yaw-design.md

## Global Constraints

50ms=25×2ms；140/5、G1、30秒、400um、450、原奖励/熵/保护。最多4初始化/640000物理子步/0更新，累计起点439；无新增历史/锚点/局部调姿，无重跑/最终测试。

## Review Focus

禁用/恢复之间不续用旧噪声；OFF不能关闭四轴或泄漏yaw积分；独立源重放必须同保持规则；初始化失败仍计尝试；主/worker退出确认后才收口。

### Task 1 噪声持续性

- [x] 新增tools/learning/persistent_exploration.py与tests/test_persistent_exploration.py。
- [x] 先验证缺失失败，再实现25周期刷新、mu/std更新、阶段/禁用/reset清空和state/RNG重放；纯逻辑必要用例已通过。绝对cycle噪声表保证配对外生输入一致。

### Task 2 被动yaw隔离与四回合执行

- [ ] 新增独立tools/validation/run_noise50_yaw.py及必要包装/测试，不改冻结旧入口。
- [ ] OFF调用FixedAdmittance原四轴方程，保持yaw内部状态0；核查同输入四轴相等。
- [ ] 绑定同一F4000模型、原物理域、明确行为合同与25周期源重放；冻结四回合登记及来源。
- [ ] 只运行±1.5°各ON/OFF，逐回合审核、无优化或入池。异常停止不重跑。

### Task 3 解释与收口

- [ ] 仅保存轨迹数学分析被动/SAC方向、实际旋转、九针同步与深度；不冒充训练改进或确定性评价。
- [ ] 核对成本/原冻结哈希及退出，保存结果/核验，更新五份滚动资料及快照，汇报后暂停。
