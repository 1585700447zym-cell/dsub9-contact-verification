# B1-05｜候选策略采集与整回合经验池适配

日期：2026-09-24。这是B.1内的限定接口增量，不是完整SAC训练器、训练准入或策略收益交付。日常查找用[项目交付总览](../../../项目交付总览.md)，当前待办用[进度跟踪](../../../项目进度跟踪.md)，汇报沿用[本月滚动素材](../../monthly_progress/2026-09/月报素材_2026-09.md)。

## 获得什么

- `CandidateCollector`调用现有`ResidualEnv`，由未训练SB3策略给出四维动作。普通采集批次结束只暂停，下一批继续同一回合；不会自动reset、重采样或把批次边界伪装成截断。
- 真实外部截断继续委托原环境执行停止及尾段审核。策略异常也尝试零动作截断；缺少完整停止证明时阻止重置。初始化、策略、停止与发布异常保留在尝试记录中，不跳过困难回合。
- `AuditedReplay`提供独立的整回合发布与PyTorch采样接口：完整校验及分配后一次替换可见状态；容量不足时逐个淘汰最旧的完整回合，不截取半个新回合；重复ID拒绝重复发布。
- 抽样保留120维观测、四维规范动作、当前/下一状态权限、实际Δt与`exp(-Δt/10)`折扣、互斥terminated/truncated。截断使用真实截止点下一状态，不把安全尾段或reset状态当bootstrap。

## 不能越过的边界

**真实候选数据始终拒绝入池。** 当前环境的隔离结果只被用于拒绝发布与诊断；采集器内部固定`training_admitted=False`，没有调用参数可以放开。正向入池及抽样测试仅使用明确标记的合成协议数据，包括有效保护失败，不能解释为真实候选获得准入。

经验池要求调用方提供明确布尔审核结果；它是可信内部接口，不是自动审核器、准入证书或安全授权系统。后续正式采集入口必须绑定已验收配置/指纹及最终回合审核，不能直接修改候选标志来运行训练。也不能直接接SB3的逐步ReplayBuffer或`SAC.learn`，绕过本项目整回合协议。

本版仅单进程、单所有者、内存存储。原子性指发布过程中校验/分配失败不暴露半个回合，不代表断电持久性、并发写入或多网络更新原子性。尝试记录、已用ID随生命周期增长，正式长训前仍需持久化与容量策略。学习循环、训练器状态恢复、正式配置、姿态/范围冻结及成本准入没有由本交付自动完成。

## 如何使用和复验

工作目录必须是`D:\dsub9项目计划\first_stage_sim\.worktrees\dsub9-v1-contact-validation`。沿用[B1-04隔离CPU环境](../learning_tensor_20260924/README.md)及其依赖锁；先选定并核对独立MuJoCo 3.13，再构建原`ResidualSession`/`ResidualEnv`。完整可运行示例见[实际未训练策略集成测试](../../../tests/learning/test_candidate_collector.py)。

已有候选环境`env`和未训练策略`policy`后：

```python
from tools.learning.audited_replay import AuditedReplay
from tools.learning.candidate_collector import CandidateCollector

collector = CandidateCollector(env=env, policy=policy, replay=AuditedReplay(capacity=10000))
collector.start('unique-development-attempt', seed=20260924)
collector.collect(4, deterministic=True)  # 批次边界不改变回合
collector.collect(4, deterministic=True, cut_at_end=True)  # 仅显式外部截断
assert len(collector.replay) == 0  # 候选数据仍全部隔离
```

这些步数、容量、小网络和种子都是诊断设置，不是正式训练超参数。完整回合可反复`collect(n)`直至`episode_finished=True`。返回值`steps`和尝试记录累计`steps`只统计成功返回的策略交互；`emergency_cut_attempts`另计异常零动作截断尝试，`emergency_cut_returned_steps`计成功返回的额外交互，`archived_row_count`计原环境归档行数（可能含错误诊断行，不等于有效样本数）。它们不包括环境内部安全尾段的物理子步，不能用一个steps字段估算全部成本。审核记录复制或发布失败时保留`pending_publication`，只能显式`retry_publication()`，不重跑策略/物理过程；未知停止状态不能靠重试发布解除。

```powershell
$env:MPLCONFIGDIR = 'D:/dsub9项目计划/first_stage_sim/.worktrees/dsub9-v1-contact-validation/tmp/learning_mpl_cache'
& 'tmp/learning_cpu_20260924/Scripts/python.exe' -X utf8 -B -m pytest -p no:cacheprovider -q tests/learning/test_audited_replay.py tests/learning/test_candidate_collector.py -o junit_family=legacy
& 'tmp/learning_cpu_20260924/Scripts/python.exe' -X utf8 -B -m pytest -p no:cacheprovider -q tests/learning -o junit_family=legacy
& 'D:/KEYANRUJIAN/python.exe' -X utf8 -B -m tools.validation.verify_native313_matrix_delivery
```

不得在本工作树运行旧插件编译测试，以免覆盖冻结DLL。新复验报告写新tag，不覆盖本目录。

## 验收与证据

本目录保留测试XML、限定判定、源码快照和滚动文档的交付时快照；具体计数见`assessment.json`和`验收记录.md`。旧清单仍保持原摘要，不因本轮新增代码改写。物理、奖励、守卫、原环境及回合缓冲实现未修改；没有重跑完整七工况矩阵，也没有独立测试、真实学习经验更新或训练后的权重。
