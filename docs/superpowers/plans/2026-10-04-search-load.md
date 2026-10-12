# SEARCH侧向载荷卸载与参考释放实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. 当前工作树原地执行，不提交/清理/新建工作区。

**Goal:** 修复负Y150搜索侧向载荷积累，在有限共同基线复验中判断是否有效。

**Architecture:** 新控制器继承风险卸载B2，SEARCH持续高侧向/总力时进入原UNLOAD；新显式会话在物理步前一次释放XY参考领先，真实位姿/速度/保护事实保持。沿用原卸载、两次搜索、20 s任务上限、功能成功/额外精度及停稳生命周期。

**Tech Stack:** 现有Python、限定MuJoCo3.13、NumPy、pytest。

**Spec:** 当前研究计划2026-10-04修订与functional_b2_20261003/负Y诊断；用户“继续修复”授权实施/有限复验。

## Global Constraints

- 新目录deliverables/task_variants/search_load_20261004；已核对原clearance120的210文件与functional_b2的216文件封存。未提交文件均保留。
- 孔径1.20 mm、功能成功、80 μm/0.5°附加精度、25 mN/2.5°保护不变。0网络、0训练、0独立测试，PAUSED。
- SEARCH中侧向力≥12 mN且总力≥22 mN持续20 ms，触发SEARCH_LATERAL_LOAD；暂停螺旋进入原UNLOAD，XY指令0，原轴向回撤/角向导纳不变。首次触发需要剩余搜索预算，否则正常失败并停稳，不额外增加次数。
- 会话在该触发后的物理步前将XY控制参考对齐当前实测XY；不改Z/姿态参考、真实qpos/qvel、物理时间、累计力/保护事实。记录前后参考/误差；不写入环境安全事件表以免污染既有恢复事件语义。未消费的参考释放请求使下一控制调用拒绝运行，避免错接会话悄悄丢动作。
- 22 mN留3 mN保护余量；旧负Y约8.318 s总力18 mN起持续上升，XY参考领先最终150–170 μm。旧已成功±X与正Y的SEARCH峰值总力最大20.822 mN，不应触发22 mN规则。此阈值来自开发资料，不是独立评价调参。
- 新预算最多5动态，累计119→124；顺序负Y150、正Y150、正X150、负X150、对准。首个负Y若不成功即停余量；任一保护/无效/初始化或运行故障/未停稳立即停止。后续普通有效失败可继续以记录回归，但不得称整组通过。旧余7不结转，不重试。
- 所有尝试先记账，500周期完整检查点，单回合1200 s墙钟上限，完整轨迹、控制事件与物理尾段；修复共用错误账对实际max_new_episodes计算余量，旧9回合默认行为不变。

## Review Focus

- 只改变控制参考，不改真实动力学状态或清除保护；释放必须一次且受运行/保护门约束。
- 无孔中心真值输入；高总力但低侧向或非SEARCH不额外触发，计时在条件解除时复位，非有限输入先拒绝。
- 搜索预算/时间/恢复限制保持；新卸载消耗已有下一次搜索资格，不能无限重启。
- 最初或检查点间异常保存最新事件，小账在大档案失败时仍反映真实5回合预算。
- 正Y已修复行为与±X结果必须复验；禁止用先验离线不触发预测冒充真实动态回归。

## Task 1: 控制器与会话

**Files:** 新增tools/control/load_search.py、tools/learning/load_session.py、tests/task_variants/test_search_load.py。
**Interfaces:** SearchLoadConfig，LoadSearchRecovery(PoseObservation)，reference_release_requested；LoadReliefSession在_command_for_action中消费一次释放请求。

- [x] 写持续/复位/预算/错误接线、非有限输入、真实状态不变/参考一次释放/保护阻断测试并见RED。
- [x] 实现最小新类，跑相关新旧检查GREEN；离线旧轨迹确认触发时间与既有成功点不触发。

## Task 2: 新预算入口与真实复验

**Files:** tools/validation/run_search_load_preflight.py；tests/task_variants/test_search_load_preflight.py；共用record_error仅动态预算余量字段小修。
**Interfaces:** 前轮完整保存机制、新5点顺序/119起点/124上限、上述会话及绑定配置。

- [x] 预算/停止/异常余量测试先RED后GREEN；一次独立只读审查并修复重要问题。
- [x] 准备静态模型、绑定输入并保存源码快照；按固定顺序执行直到完成或预定停止。

## Task 3: 诊断与交付

- [x] 离线独立复核功能/严格精度、停稳、载荷和参考释放；成功仅限已执行工况，失败不隐去。
- [x] 更新入口、进度能力与原八项/风险/下一项/日志、总览、10月月报和研究计划；保存文档快照和新封存。

## 执行裁定

已有用户执行授权内直接推进；用本交付progress.md记账，不执行依赖提交的bash脚本。相关测试不隐式增加历史长动态/旧运行库测试预算；本轮控制代码独立新模块，旧实验可从封存源码复现。可交付阶段完成或新问题时报告，不扩展到训练。

## 实际收口

2026-10-04 00:48：81项相关检查通过；实际1/5，首例负Y无保护但SEARCH_BUDGET_EXHAUSTED，功能未通过，余4关闭、累计120。其余四点未执行。勾选表示实施与依预定规则有限验证/归档完成，不表示修复性能或B.2验收。执行时计划原文在source_snapshot，后续研究下一项转为导纳积分/参考状态一致性。
