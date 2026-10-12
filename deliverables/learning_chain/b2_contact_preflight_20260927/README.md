# B2-06｜有限接触开发预检

2026-09-27。用户同意继续B2-05提出的有限接触开发预检后执行。本项不修改模型、基线控制、奖励、观测、守卫或成功标准，不运行SAC更新，不使用独立测试。范围仅为已登记零倾角离散点；**`training_admitted=false`，`domain_qualified=false`**。

**收口结论：计算/停止与信息门通过，局部位移门7/8，未全过；本次不是新增训练准入。** 局部位置差仅0.871—6.129nm，但有约0.488—0.811mN的接触力矢量响应。完整解释、口径与下一项判断见[结论与边界](结论与边界.md)，[下一项8回合建议](下一项建议.md)尚未执行。

## 实测与门检查

实际9次初始化、17个完整动态尝试。零残差9点结果分布：{'FULL_SUCCESS': 4, 'TASK_FAILURE': 5}；8脉冲结果分布：{'TASK_FAILURE': 2, 'FULL_SUCCESS': 6}。所有已尝试项均保留；未执行项：[]。

机器复算门：`{'accounting_complete': True, 'computation_stop': True, 'information': True, 'pulse_physical_effect': False}`。这些门分别核对完整记录、可信计算与停止、合法反馈可检测差异、指定脉冲的实际运动作用。通过不等于装配全部成功、策略有效、连续域可信或接触学习已准入。

| 动态ID | 任务结果 | 接触周期 | 最终XY误差/μm | 周期峰值力/mN | 实际停稳 |
|---|---|---:|---:|---:|---|
| zero_center | FULL_SUCCESS | 0 | 0.000 | 0.000 | True |
| zero_x_neg_75 | TASK_FAILURE | 0 | 75.000 | 0.000 | True |
| zero_x_pos_75 | TASK_FAILURE | 0 | 75.000 | 0.000 | True |
| zero_x_neg_100 | TASK_FAILURE | 2418 | 61.099 | 24.474 | True |
| zero_x_pos_100 | FULL_SUCCESS | 3212 | 12.295 | 24.474 | True |
| zero_y_neg_75 | TASK_FAILURE | 0 | 75.000 | 0.000 | True |
| zero_y_pos_75 | TASK_FAILURE | 0 | 75.000 | 0.000 | True |
| zero_y_neg_100 | FULL_SUCCESS | 2809 | 41.415 | 24.474 | True |
| zero_y_pos_100 | FULL_SUCCESS | 3691 | 17.290 | 24.474 | True |
| pulse_x_neg_100_neg | TASK_FAILURE | 2425 | 61.272 | 24.479 | True |
| pulse_x_neg_100_pos | TASK_FAILURE | 2394 | 50.898 | 24.478 | True |
| pulse_x_pos_100_neg | FULL_SUCCESS | 3207 | 11.460 | 24.479 | True |
| pulse_x_pos_100_pos | FULL_SUCCESS | 3238 | 19.610 | 24.479 | True |
| pulse_y_neg_100_neg | FULL_SUCCESS | 2813 | 41.218 | 24.479 | True |
| pulse_y_neg_100_pos | FULL_SUCCESS | 2797 | 36.533 | 24.479 | True |
| pulse_y_pos_100_neg | FULL_SUCCESS | 3696 | 16.710 | 24.479 | True |
| pulse_y_pos_100_pos | FULL_SUCCESS | 3704 | 16.715 | 24.479 | True |

零残差与脉冲组点位构成不同，不直接比较两组成功率。脉冲仅覆盖四个100μm沿轴点的两个符号；必须逐点与各自零残差比较。有限、有效且停稳的保护退出仍属于失败。

## 信息是否可区分

以下比较同幅度相反符号的零残差轨迹，以相同时间且双方均有动作权限的周期为口径。策略力矩历史来自白名单前24维，不使用真实孔误差作为输入。判据为归一化力矩历史最大分量差>1e-6，连续至少3个控制周期，X和Y各至少一对满足。

| 对称点对/μm | 共同有效期最大差 | 连续可区分周期 | 信号门通过 |
|---|---:|---:|---|
| x ±75 | 0 | 0 | False |
| x ±100 | 0.349214 | 2634 | True |
| y ±75 | 0 | 0 | False |
| y ±100 | 0.369025 | 3122 | True |

这只证明指定仿真轨迹中存在可检测信号，不证明噪声下方向估计准确、完整可观测或严格马尔可夫。两个不同初始点产生不同合法力矩，可支持继续研究纠偏，但还需训练和评价验证策略是否利用这些信息。

## 动作是否改变实际运动

每个脉冲由合法M点力范数连续3个控制采样>1mN且有权限触发，请求幅值±0.25，最多100个2ms周期。失去权限立即终止，恢复后不重触发。两符号均预先登记，不按真实偏差选择有利方向。触发前与零残差的实际位置差须<1e-12m；触发后固定0.2s比较实际三维位置，不用命令积分替代实际运动。

| 脉冲ID | 已触发 | 对照窗口最大实际位置差/μm | 请求满0.2s | 超过1nm分辨门 |
|---|---|---:|---|---|
| pulse_x_neg_100_neg | True | 0.005 | True | True |
| pulse_x_neg_100_pos | True | 0.006 | True | True |
| pulse_x_pos_100_neg | True | 0.004 | True | True |
| pulse_x_pos_100_pos | True | 0.001 | True | False |
| pulse_y_neg_100_neg | True | 0.004 | True | True |
| pulse_y_neg_100_pos | True | 0.004 | True | True |
| pulse_y_pos_100_neg | True | 0.004 | True | True |
| pulse_y_pos_100_pos | True | 0.004 | True | True |

实际位移差、完整触发时刻、权限及末端差异见[assessment.json](assessment.json)。超过分辨门只能证明动作有作用；末端差异可能同时包含后续基线响应，不能视为瞬时残差的直接位移，更不能直接声称改善成功率。

![零残差与脉冲对照](figures/01_零残差与脉冲物理作用.png)

## 版本、成本与复验

单进程执行总墙钟3523.48s，包含本次串行尝试及归档/输入核查；不含前置测试、审查和后续分析。每回合单独记录成本，初始化不是装配回合。期间有独立只读分析，故不作为机器独占的纯物理吞吐基准。全过程绑定既有872项生产/配置输入及本项探针脚本，前后相同；不覆写旧训练准入。

[协议](protocol.json)在运行前写入，所有原始记录见[runs](runs/)，逐项结果见[attempts.json](attempts.json)。归档重算重新验证动作触发/权限、实际停止、计数及信号/物理作用门，不重新积分物理。无效与未完成尝试不删除、不重采样。生产学习代码未改；本次测试与审查详情见[实施记录](实施记录.md)，历史443项完整学习测试不当作本次重跑结果。

```powershell
$env:MPLCONFIGDIR='D:/dsub9项目计划/first_stage_sim/.worktrees/dsub9-v1-contact-validation/tmp/learning_mpl_cache'
& tmp/learning_cpu_20260924/Scripts/python.exe -X utf8 -B deliverables/learning_chain/b2_contact_preflight_20260927/checks/analyze.py --check
```

原运行入口拒绝覆写已有runs目录；不要删除已交付目录来复跑。新物理复验必须用另一个版本化输出包并明确重新登记。

## 学习问题与下一项

本项只交付有限接触预检及它的负结果。后续是否进入新的普通SAC短训，取决于信息、作用、计算/停止门和零残差B2尚存不足，不能仅因存在接触就启动训练。新的离散训练/开发清单、来源/参数冻结、经验准入和成本预算需另行完成，原±50μm资格不自动扩大。

当前决定和下一项见[项目进度](../../../项目进度跟踪.md)，成果入口见[交付总览](../../../项目交付总览.md)，本月统一汇报见[九月滚动月报](../../monthly_progress/2026-09/月报素材_2026-09.md)。
