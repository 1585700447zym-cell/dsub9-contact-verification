# SDD ledger — plan: docs/superpowers/plans/2026-10-04-paper-protocol-v4.md

用户“继续”承接 TV-09 后论文公平比较准备。分支 feature/dsub9-dynamic-actuator-v1；起点187项脏/未跟踪记录；保留所有旧修改。

Pre-flight: Task 1 提供共同配置指纹/指标 schema，Task 2 只读转换TV-09五回合；Task 3 不修改封存输入。无新物理接口实现，无运行中训练。

Ruling: 失败耗时统一罚26秒（25秒动作+最多1秒裁决）；成功者平均时间只作描述指标；缺失/无效尝试使比较不可用，不能因删样本得到优势。

Ruling: 旧轨迹无每控制周期子步峰值序列；只报告已有全回合物理峰值和明确标注的2ms采样力时间积分，不伪造子步载荷积分。

Task 1: in progress — 协议与离线检查；新动态0、训练0。

Task 1: complete — 新模块缺失导致RED，随后25项GREEN；保护失败测试的虚构CONTACT_FAILURE名称在实现前纠正为既有CONTACT_GUARD。

Task 2: audit tooling correction — 第一次读取摘要比对错误地要求归档包含自身SHA。实际只有ledger追加archive_sha256，其余字段逐值相同。按既有归档契约分别核验外部SHA和内部摘要；保留首次失败日志，不改源归档。

Final review: fresh independent reviewer /root/paper_protocol_review, gpt-6-astra/high；初评0 Critical / 2 Important / 0 Minor。

Final: fixed 失败类别与事实矛盾可绕过资格门 — 6个反例RED→GREEN；独立guard事实和完整裁决优先级。

Final: fixed 共同依赖指纹遗漏 — 5个依赖/评价/runtime/初始位姿反例RED→GREEN；合计36项新模块检查通过，相关套件待最终结果。

Ruling: 保守绑定原执行依赖（排除可变收口计划），额外绑定评价源码及runtime证明；可能多拒绝无关旧文件变化，但不会漏掉已知的实际控制/裁判依赖。没有延期Minor。

Task 2: complete — 2112个历史封存文件通过，5个基线指标重算；16563零命令等价、132504反事实发现6越界。物理/训练0。
Task 3: complete pending seal — 独立审查及相关检查完成，五份滚动资料更新。

Final: verification complete — 272相关检查通过；2 Important均经RED→GREEN修复，独立审查为全新上下文；无延期Minor。共同输入、2112历史文件、5归档指标和新链接均通过。
