# B1-09｜限定工程范围的B.1收口包

2026-09-26。实际判定以[admission.json](admission.json)中的`training_admitted`及全部7个`gates`为准；任何false、缺项或当前指纹不符均拒绝准入。本文不代替机器检查，不把文件存在当成通过。

## 本包交付什么

1. [范围与姿态参数记录](../../../docs/stage_b/工程范围与姿态参数冻结记录_v1.md)：只限XY各±50μm、初始零倾角的工程链路试训。2.5°固定为操作性检测/停止触发值，不是模型可信上界或硬角度上限；原联合守卫、数值有效性和真实停止审核全部保留。
2. [显式首训配置](config.json)：CPU单工作进程、2ms策略周期、20,000控制周期目标、完整回合审核后结束；256批量、两层256网络、学习率3e-4、5000已审核转移预热、100000池容量、每4条已审核转移最多1个梯度批次、明确熵和按实际Δt折扣。工程初值，不声称最优。
3. 正式无需学习的准入入口：核查真实依赖/DLL和实际环境参数，复算已有26/8次预检及14回合基线归档，运行当前完整接口测试，绑定源码、测试、配置、范围、成本与证据；缺失/失败始终写false，不修改历史归档。
4. [独立成本报告](../b1_cost_20260926/README.md)：3065控制周期、1863接触周期，普通任务失败但有效停稳。没有经验发布或优化器步进。采样及记录约36.105ms/周期；33,000周期预测约19.9分钟，网络反向代理约1.3分钟，另加约10.966秒/回合的重置、终审与压缩归档。首次预留60分钟，不保证最坏耗时。

正式准入为B.1接口的限定资格，不是现成的训练器。旧候选会话、采集器及历史经验仍拒绝学习；B.2必须实现并验证准入采集—SAC更新—保存加载—评价及训练状态恢复，不能简单翻转历史false标记。本包没有SAC更新、训练权重、收益或独立评价。

## 实际证据怎么查

| 内容 | 文件 |
|---|---|
| 7个门、错误、源码/运行时/证据摘要 | [admission.json](admission.json) |
| 正式入口执行的完整接口结果 | [测试XML](learning_tests.xml)、[原始输出](learning_tests.log) |
| 26次预检与8回合边界原始复算 | [26次记录](recheck_archives.log)、[8回合记录](recheck_scheduled.log) |
| 旧112文件/14回合实际停止复核 | [基线核验](native_archive.log) |
| 成本逐项耗时和完整重复轨迹 | [成本数据](cost.json)、[原始回合](timing_episode.json.gz) |
| 先失败再通过、审查修复、排除范围 | [核验说明](checks/核验说明.md)、[本轮各次测试](checks/test_runs/) |
| 不可变交付清单 | [manifest.json](manifest.json)，源码快照通过admission转递绑定 |
| 当前状态/交付/月报快照 | [document_snapshot](document_snapshot/)；后续查根目录滚动文件 |

旧资料的false状态保留其归档时点。本包另行记录限定资格，不追认历史数据为可学习。14回合、26次预检和8回合不是本次重新积分的新增样本；成本重复也不计入工程覆盖率。完整目录测试数包含本轮新增专项，不把历次测试数相加。

## 使用与复核

始终使用现有工作树：`D:\dsub9项目计划\first_stage_sim\.worktrees\dsub9-v1-contact-validation`，保留所有未提交成果。使用项目独立CPU解释器，不能直接换为旧用户环境。

交付完成后只读复核（不重新积分、不训练）：

```powershell
$env:MPLCONFIGDIR='D:/dsub9项目计划/first_stage_sim/.worktrees/dsub9-v1-contact-validation/tmp/learning_mpl_cache'
& 'tmp/learning_cpu_20260924/Scripts/python.exe' -X utf8 -B deliverables/residual_interface/b1_closeout_20260926/checks/recheck_closeout.py
```

重新执行整个B.1检查时使用**不存在的新输出目录**。成本文件必须与当前代码和运行时相符：

```powershell
& 'tmp/learning_cpu_20260924/Scripts/python.exe' -X utf8 -B -m tools.validation.verify_residual_interface `
  --output deliverables/residual_interface/b1_closeout_NEW_TAG `
  --config docs/stage_b/工程短训配置_v1.json `
  --cost deliverables/residual_interface/b1_cost_20260926/cost.json `
  --package tmp/mujoco_3_13_probe --seed 2026092609
```

此命令实际跑测试并产生新准入记录，不训练。异常尝试同样保留，不覆盖旧tag。当前代码变化后，旧准入拒绝当前运行是预期行为，不表示旧归档应被改写；应登记B.2的新指纹和相关回归，再决定哪些既有证据可以沿用。

程序调用方应使用`verify_admission`，传入交付清单固定的准入摘要、当前`qualified_runtime`与`all_sources`结果；并对每次初始化执行`validate_case`。不能只读取`training_admitted=true`一个字段。最终接线和防绕过测试在B.2完成，本包不宣称该接线已存在。

## 保留限制与下一阶段

- 没有连续域、任意策略、初始±1.5°、触发瞬间同时接触或普遍超调上界的证明。D壳、弹性、真实载荷、机器人/夹爪、实物迁移后置。
- 单条轨迹成本不是最坏情况；网络代理不含优化器步进、经验抽样、逐步策略推理或训练恢复。33,000为正常预测，诊断看门狗之后还可能有1500周期停止尝试；周期看门狗不保证原生挂死/磁盘故障等情况下的墙钟停止。
- 本轮审查重点是新增工具，不重新认证全部继承物理；历史观察器等次要缺口仍保留。旧SDF编译测试未执行，旧14矩阵未重积分。散列用于可复现与变更检测，不抵抗有权改源码和可信摘要的恶意本地作者。
- B.2先交付绑定正式准入的真实经验采集、最小SAC更新和完整训练状态保存/恢复，再按显式配置执行工程短训及固定开发评价。初始倾角扩展和最终独立评价不提前作为首训前置；短训也不等于原任务6整体验收。

进度和月报维护同一份滚动文档，不另建本阶段月报或PPT。
