# B.2 actor率对照执行适配与协议准备

2026-09-30。沿用指定工作树及feature/dsub9-dynamic-actuator-v1，保留全部原修改。本项接通执行代码并验收纯协议；**尚未运行真实数值验证、A学习复现、训练或物理评价，也没有证明修复有效。B.2未完成。**

## 已接通的路径

- [显式分支与授权合同](../../../tools/learning/actor_lr_contract.py)：A actor=3e-4，B=3e-5，critic/温度=3e-4。共同输入为[严格origin_v2](../b2_actor_lr_origin_20260930/origin_v2/manifest.json)的四预热22766行及固定500批抽样。不追加训练采集，不更改奖励、阈值、幅度、域或种子。
- [独立持久账本](../../../tools/learning/actor_lr_budget.py)：先刷盘预约再采样/计算；异常尝试仍计费、不重试。恢复校验阶段、门、顺序、逐条成本及终结结果；拒绝其它候选/授权和过期内存覆盖新账本。
- [离线学习与完整恢复](../../../tools/learning/actor_lr_engine.py)：完整来源、边界索引、网络、三个Adam、温度、计数、随机流、历史和分支绑定。A500批必须逐值复现旧train_03，只有身份和墙钟耗时排除；不符停止，B不能绕过。固定B500后冻结，不挑选中间策略。
- [真实验证与评价适配](../../../tools/learning/actor_lr_execution.py)：未来先运行4个私有事务和8个测试状态前向，覆盖独立actor率、无权限屏蔽、注入回滚、保存恢复/跨分支拒绝。全部通过后才A→B；随后对相同256状态做initial/A/B分布诊断共768状态，无额外critic。各固定检查点在新进程恢复，A四点结束才B四点；任意保护完整归档停稳后停止整轮，普通任务失败保留。
- [监督入口](../../../tools/validation/run_actor_lr_comparison.py)：授权先于runtime/模型/claim；登记父进程与独占启动。持续检查直接父、祖先监督者、全轮停止请求及持久账本。监督树停止不能确认时保留账本、记录未收口，不能冒称已停止或重置成本。

## 验证与负记录

最终统一216项协议检查全过，见[结果](final_protocol_results.json)、[JUnit](final_protocol.xml)、[阶段验收](assessment.json)；监控模型前向/Adam.step/原生物理均0。包含前项133项范围及本项拒绝/恢复/执行次序反例，历史和中间运行不能相加。实际SAC全量数值与物理检查因预算尚未批准而没有运行；模拟站位不能当真实学习证据。

独立审查发现的阶段造假、授权错配、A/B键错配、边界索引遗漏、阶段回退、监督未收口与祖先停止、诊断摘要缺口均修正，相关红/绿记录留存，见[审查](review.md)。首个测试命令使用了不存在的解释器路径，改为原CPU环境后运行；没有计算或改环境。原286源、45前项产物、4149旧封存和929旧源码原字节保持。

## 执行门与预算申请

[candidate.json](candidate.json)是协议准备候选；[摘要](candidate_pin.json)、[预检](preflight.json)、[未批准申请](authorization_request.json)随后封存。它明确real_validation_required=true。没有authorization.json、没有run目录，不以协议准备代替真实验证资格。

只读检查命令：在本工作树，用`tmp/learning_cpu_20260924/Scripts/python.exe -X utf8 -B -m tools.validation.run_actor_lr_comparison --candidate-sha256 <candidate_pin.json中的摘要> --verify-only`。该模式不执行模型或物理，也不授予计算权。

真实启动须单独批准新候选及上限：合成事务最多16、测试状态前向最多128（当前计划实际4/8），分布诊断768状态、A/B正式各500批、各四点最多8动态，既有57加本项最多65；每回合13000周期看门狗。全部门通过也只形成早期开发筛选，B须保持原初始4/4，优于退化A不足以称恢复；不能证明2500批在线危险状态问题已修复或独立泛化。

**旧余19次/2000批不结转、不执行；自动跟踪PAUSED。** 真实计算未批准，按项目阶段约定本项汇报后暂停。原三份滚动文档已同步；历史包、合同和阈值保持。

