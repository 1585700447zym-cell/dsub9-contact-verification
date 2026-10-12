# 小边界数值集成门实施计划

> 使用superpowers:executing-plans inline，逐项TDD。沿用原工作区，保留未提交修改，不提交、不清理。只实施本计划的离线准备，不执行最后的数值计算步骤。

**Goal:** 提供可审阅、缺授权先拒绝的F12p5数值集成脚本，供后续最多4合成更新事务/32测试状态的一次性验证。

**Architecture:** 新目录small_boundary_numeric_gate_20261007调用封存PC-12适配及原完整SAC/回放/检查点核心。父进程与独立读取进程共享授权身份和全局预算；纯合成档案有明确synthetic身份，不使用历史训练数据，不构造物理环境。

**Tech Stack:** 现有Python/NumPy，未来明确授权后用PC-06独立CPU解释器、torch/SB3；不增依赖。

**Spec:** [PC-12数值门](../../../deliverables/paper_comparison/small_boundary_execution_20261007/数值门清单.md)，[PC-11设计](../specs/2026-10-07-small-boundary-fair-comparison-design.md)。

## Global Constraints

- 当前数值/训练/物理计算无新授权；本轮真实构造、读取张量、推理、更新、物理均0，累计208、PAUSED。
- 只在新目录实现；765旧封存文件（含PC-12的35份）和1057共享输入保持。
- 后续唯一额度：父3批、reader1批，总4合成批；父16/reader16个显式测试状态前向，总32。训练事务内部前后向计入事务工作，不伪装为显式测试状态。
- 实际零起点、空优化器/回放、参数/Adam/回放/终末边界/采样/RNG及下一步恢复待该门真实验证，当前不签发资格。
- 正式物理backend不属于本轮，21动态/2000正式批仍关闭；合成语义flags不是停稳实测。

## Review Focus

- 伪造旧授权、换输出目录重复领取、child独立开户必须拒绝。
- 初始化/导入torch/张量读取前需要有效授权；错runtime/来源/profile先拒绝。
- 更新/前向先计费，失败关闭余量，禁止不计费的直接actor调用。
- 合成a不能变成0.25a进入回放/critic；inactive动作0、warm held RNG与原核心一致。
- 保存与新进程恢复比较除墙钟时间之外的完整状态；没有真实执行不能称数值通过。

## Task 1：授权、预算与runtime纯绑定

Files: 新目录numeric_contract.py、test_numeric_contract.py。
Interfaces: `verify_numeric_authorization(candidate,grant,expected_grant_digest)`、`NumericLedger.create/load/reserve/complete/fail`、`verify_runtime_files(runtime)`；都不导入torch/native模块。

- [x] 写缺授权、超额、跨目录重复、child越权、来源/runtime错配反例，运行纯pytest看RED。
- [x] 实现父3/reader1更新及16/16显式前向持久化计数、按授权摘要排他领取；运行GREEN。

## Task 2：合成数据与独立恢复脚本

Files: 新目录synthetic_data.py、numeric_worker.py、test_numeric_protocol.py。
Interfaces: `synthetic_episode(chain,stage,index)`产生全新80周期合成档案；`execute_numeric(candidate,grant,...)`须先验授权再连接CPU runtime、调用PC-12组合器，父2更新→完整保存→父下一更新与reader下一更新对照；显式状态各16次。

- [x] 写纯协议/a与物理量/完整奖励/一次warm取样/未授权CLI拒绝反例，运行RED。
- [x] 最小实现；通过纯检查和静态调用次序审核。实际critic输入钩子、张量状态逐值比较代码不执行。

## Task 3：候选、独立审查与收口

Files: 新目录prepare_candidate.py、verify.py、结果说明.md、review.json及快照；更新原五份滚动资料。

- [x] 保存未授权候选及实际用量0，绑定765旧封存、1057输入、CPU解释器/DLL/版本元数据；运行关联纯检查。
- [x] 一次限定独立审查；Important/Critical作者一轮RED→GREEN修复，无二审；封存并报告。

## 待明确计算授权后才执行

- [ ] 实际CPU零起点、新合成400条回放、4更新事务、32测试状态、完整落盘、新进程恢复及逐值对照；这一步本轮不执行。失败关闭余额，无重试。
