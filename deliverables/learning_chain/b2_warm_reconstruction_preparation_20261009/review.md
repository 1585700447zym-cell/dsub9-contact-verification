# SCOPE15 独立代码审查

当前阶段：B.2第3项；任务：状态重建数值门离线候选审查，已收口。

使用 requesting-code-review 技能，由独立只读审查代理 `/root/b2_warm_restore_review` 对本目录功能代码、测试、实施说明及原 V4 学习／检查点／回放实现进行比对。审查未执行科学计算运行时，未修改文件；修复由主代理实施。

## 发现及修复

1. **I1，Important，已关闭。** 原 `state_digest` 对字典未编码成员数，外层字段移入最末嵌套字典可保持相同摘要，因而不足以证明完整结构相等。新增 `test_state_structure.py` 通过 AST 提取真实摘要函数，标准库反例在 `red_structure.log` 中失败；加入字典长度标记后，结构区分、字典重排等价、数字类型与序列边界三项通过，见 `green_structure.log`。审查代理复核关闭。旧归档不改，新门自行比较新摘要，不复用旧摘要值作为结构等价证明。
2. **I2，Important，已关闭。** worker 持账本锁时被硬截止杀死，原关闭路径会因遗留锁再次超时而跳过授权关闭收据。`finalize_execution` 现先核对监督器的进程树／启动器退出证据；仅在二者都确认为真时处理遗留锁。账本关闭失败仍独立写入授权关闭收据、错误及 `CLOSED_ERROR`；`Gate.verify` 拒绝已有关闭收据。`fixture_orphan_lock.py` 真实持锁后由拥有的 Windows Job 终止；`test_failure_closure.py` 同时验证无退出证明时保留锁、仍写失败收据。反例先失败于 `red_orphan.log`，修复后两项通过于 `green_orphan.log`。审查代理复核关闭。

## 最终审查结论

独立审查结论：I1、I2 均已修复复核；无未解决的 Critical、Important 或额外 Minor，可以进入离线候选收口。

已比对原算法的回放顺序、终末边界、388次四维随机抽样、零更新状态和独立 reader 重建流程；未发现额外学习器构造、读取或前向路径。

结论范围不包括实际 Torch／NumPy 状态相等性、可训练 V4Chain、`_audited_warm_rng` 的线上接入、策略效果或新训练准入。最终候选摘要、完整回归及封存由主代理核验。失败反例及故意遗留的测试锁保留在 test_work 中作为历史测试证据，均不是真实训练运行授权或活动进程。
