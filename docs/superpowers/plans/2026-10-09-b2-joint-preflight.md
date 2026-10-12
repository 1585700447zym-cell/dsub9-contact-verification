# B2-SCOPE-09 联合点预检实现计划

Goal: 落实 SCOPE-08 的固定 12 项候选，仅实现和离线检查；交付可单独审批的物理执行申请。

Spec: `deliverables/learning_chain/b2_joint_admission_design_20261009/准入方案.md` 与 `admission_proposal.json`。

Architecture: 新交付目录复用 SCOPE-05 监督、归档和数值审核源码；新建动作日程、单次恢复夹具与覆盖审核。生产代码及全部旧封存不改。

Tech stack: Python 标准库；离线数值回归仅加载既有绑定 NumPy 与明确选择的纯数学定义。

Global constraints: 现有工作树/分支，保留全部未提交修改；不提交、不清理、不建工作树；本轮环境/reset/物理积分/学习器/张量读取/前向/优化/经验发布均 0；动态累计 225；自动跟踪 PAUSED。新候选登记不等于执行授权。旧 grant 不继承。

## Task 1: 固定日程与恢复夹具
- [x] 写离线失败测试，再实现 `scope_contract.py` 与 `recovery_fixture.py`。
- [x] A 408 / B 816 周期、全局索引与掩码、固定 12 项顺序。
- [x] 单次触发在准备后的首段 SEARCH；丢弃缓存命令，原停止流程；缓存重建不得再次更新基线或伪造传感器。
- [x] 纯注入状态测试包括拒绝、超时、锁存、恢复后首周期。
Interfaces: fixed specs + `profile_action(profile, cycle, enabled)` + fixture `prepare(session,snapshot,refresh)` / `action(snapshot, recovery_state)`；worker 和 auditor 都消费同一冻结合同，但独立验证原始证据。
Expected: 先缺少模块失败，之后纯逻辑测试通过，无引擎导入。

## Task 2: 接入监督、审核与成本门
- [x] 复制并有边界地适配旧监督/worker/审核；固定新路径、新版本、新 scope key、新 claim。
- [x] 写预算/授权反例测试，拒绝旧授权和请求本身，失败立即关闭固定分母。
- [x] A/B 接触有效方向、两种保持块、力峰重叠；力矩/穿透单列。
- [x] R 源快照、一次触发、回撤/重锚/第二 SEARCH、掩码与首周期动作逐项校验。
- [x] worker 的注入恢复发生在内部准备返回前，保持前后周期/观测来源连续；不伪造历史原始档案。
Interfaces: Task 1 返回请求与 fixture 事件；worker 原始 schema 加 fixture 证据，auditor 独立重算；execute_matrix 固定 12 动态 / 0 静态。
Expected: 离线正反例通过；未授权 CLI 在物理导入前拒绝；原绑定输入仍匹配。

## Task 3: 复核、绑定与交付
- [x] 保存旧文档与 git 状态，新的代码/运行时/方案绑定。
- [x] 对旧真实档案回归继承审核数学（只读，无仿真），明确它不能变成新覆盖。
- [x] 一次独立代码审查；重要问题补失败测试并修复。
- [x] 更新五份滚动文档并保存六份不可变前后快照；保留历史封存。
- [x] 最终 check-only、离线测试、来源/封存校验；封存新的申请与报告。
Expected: 实现离线验收通过，执行请求仍未授权，无新物理/训练；完整 B.2/C 仍未验收。

## Review Focus
未运行新物理路径；重点检查多层 prepare 的缓存/观测刷新、首次恢复后驱动参考与净推进起点、已有 guard 的优先级；预算 claim 与异常关闭；动作日程是否暗用 case 真值；峰值和接触口径是否被稀释；valid guard failure 是否被错当无效而删除。

## Workflow adaptation
用户明确保留未提交修改，因此不使用要求 commit/clean 的脚本；在新交付 `progress.md` 记录同等步骤和结果。已有具体方案及继续实现授权，常规步骤不重复请示。阶段结束暂停汇报。
