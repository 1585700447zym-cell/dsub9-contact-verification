# B2-SCOPE-21 四点效率差异离线归因实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 只用已封存F0/F2000四点档案解释耗时与终末精度变化，给出有证据的路线决定。

**Architecture:** 使用标准库读取8份gzip/JSON，不导入项目运行时。用输入观测的同周期阶段解码、控制事件与真实trace对齐半开周期，再核对动作、奖励和终末状态；记录描述性证据与未验证的因果解释。旧合同、算法和历史结果不修改。

**Tech Stack:** 已有CPU解释器，Python标准库gzip/json/math/csv/hashlib/unittest；模型、物理、优化、网络推理均0。

**Spec:** [SCOPE20已明确的下一项](../../../deliverables/learning_chain/b2_joint_sac_continuation_execution_20261009/结果说明.md)及根目录AGENTS.md。用户“继续”批准该离线任务。

## Global Constraints

- 使用既有worktree和feature/dsub9-dynamic-actuator-v1；HEAD及223条既有dirty记录保持，不提交或清理。
- 不加载张量或调用科学库、策略/critic；新增物理、推理、更新、经验发布均0，累计动态254、自动跟踪PAUSED。
- F0不是纯B2；四点均为已用开发资料，单训练种子；10%开发继续判据和原3处覆盖缺口保持。
- 不改功能成功历史标签；80μm/0.5°为既有附加精度口径，单列其实际结果与奖励/判据关系。
- 更新5份滚动文档并保存其及AGENTS的6份快照；不把滚动原件作为不变输入。

## Review Focus

- 输入观测阶段与左侧trace的阶段可能差一个周期；以输入观测为准，并检查事件边界。
- task_end与audit_end不同；停止确认计入任务耗时，剩余审核尾段另列，奖励全档案与任务段分列。
- SEARCH入口状态已受INSERT残差影响；路径对照不作为独立的演员因果干预。
- 命令积分与真实位移不同；同时列实际轨迹、参考、权限、预测/执行一致性和即时命令干预。
- 功能成功不是附加80μm精度通过；若奖励不含附加精度，只报告目标不一致，不伪造反事实训练结果。

## Task 1: 登记来源与纯分析函数

**Files:** 新建deliverables/learning_chain/b2_joint_efficiency_diagnosis_20261010/{register.py,analyze.py,test_analysis.py,progress.md}。

**Interfaces:** 登记输出registration.json含SCOPE20 seal、8档案及相关奖励/判据/观测/动作源码sha、6文档before pins；analyze提供phase_of、time_parts、reward_parts、motion_stats、validate_alignment纯函数。

- [ ] 核对SCOPE20封存和关闭，保存before文档、分支/HEAD/dirty记录。
- [ ] 先写并观察失败测试：输入阶段优先、任务尾段隔离、部分周期时间裁剪、非法onehot、非单调时钟、最大进展奖励不重复、真实零运动不能由命令积分替代。
- [ ] 实现纯函数并执行标准库测试；Expected: 所列测试通过，无科学模块导入。

## Task 2: 实际8档案归因与路线报告

**Files:** analyze.py产出diagnosis.json、phase_summary.csv、cycles.csv、search_alignment.csv；新建build_report.py、结果说明.md、路线决定.md。

**Interfaces:** 消费registration.json及8档案；诊断输出每段时间、路径/载荷/4维命令、奖励分解、终末精度和同比差值。

- [ ] 核对137维观测、n动作/转移与n+1 trace、dt、逐周期权限/命令、冻结来源及奖励公式；Expected: 所有8档案可比且自洽。
- [ ] 按task截止分解时间，导出完整周期及搜索elapsed/theta对照；用真实运动核对J01/J02变化。
- [ ] 单列80μm/0.5°附加精度，并核对冻结功能判据与奖励源码，不改旧标签。
- [ ] 写证据、可支持的机制解释、不能识别的学习原因和下一条最小路线；Expected: 描述性与因果结论明确区分。
- [ ] 一次新上下文限定独立审查分析及报告，修复实质发现。

## Task 3: 文档整合与封存

**Files:** 新建publish_delivery.py、verify_delivery.py；更新既有5份项目滚动文档，保存document_snapshots/6份。

- [ ] 发布前按before pins检测并发编辑，更新能力表、原八项对应、风险、下一项、月报综合摘要/数字/负结果/图表/来源日志。
- [ ] 只读核对SCOPE20及此前3685个封存成员、2655来源输入、当前阶段数据和快照；封存新阶段。
- [ ] 报告实际结论和限制，阶段完成后暂停；Expected: 无新科学执行或自动准入。
