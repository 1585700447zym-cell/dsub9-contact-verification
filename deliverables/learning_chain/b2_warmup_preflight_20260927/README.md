# B2-10｜代表性预热探索候选预检

B2-10启动8/8回合，归档8回合；8个有效停稳且未触发保护，完整成功6个，未执行0个。8回合均满足预检条件，仅支持下一项小规模接触学习方案和准入版本审查，尚未授予训练资格。

本项是开发候选预检，新增SAC更新0、经验发布0、独立测试未用。成功个数只是这些已启动随机预热尝试的描述，不代表SAC策略收益。

## 冻结方案与全部尝试

四个沿轴100μm、零初始倾角点，固定负X、正X、负Y、正Y顺序，每点种子2026092709、2026092710。四维独立均匀[-1,1]、float32、PCG64/SeedSequence([seed,1])，每2ms生成一次，屏蔽阶段也推进随机流。动作由原INSERT/SEARCH权限和原共同限制决定是否生效；没有5μm触发或有利窗口筛选。

| 点位 | 动作种子 | 任务结果 | 有效停稳无保护 | 接触周期 | 有效命令周期 | 最终XY(μm) | 峰值力(N) | 墙钟(s) |
|---|---:|---|---|---:|---:|---:|---:|---:|
| x_neg_100 | 2026092709 | TASK_FAILURE | 是 | 2416 | 3990 | 50.2644 | 0.024475 | 212.189 |
| x_neg_100 | 2026092710 | TASK_FAILURE | 是 | 2376 | 3949 | 63.5063 | 0.0244797 | 209.626 |
| x_pos_100 | 2026092709 | FULL_SUCCESS | 是 | 3227 | 4780 | 20.6891 | 0.0244754 | 229.705 |
| x_pos_100 | 2026092710 | FULL_SUCCESS | 是 | 3196 | 4761 | 2.93372 | 0.0244796 | 227.185 |
| y_neg_100 | 2026092709 | FULL_SUCCESS | 是 | 2760 | 4334 | 21.0849 | 0.024475 | 229.29 |
| y_neg_100 | 2026092710 | FULL_SUCCESS | 是 | 2754 | 4326 | 34.5477 | 0.0244796 | 229.515 |
| y_pos_100 | 2026092709 | FULL_SUCCESS | 是 | 3674 | 5245 | 21.4389 | 0.0244755 | 263.276 |
| y_pos_100 | 2026092710 | FULL_SUCCESS | 是 | 3695 | 5250 | 14.0333 | 0.0244795 | 282.26 |

未执行项：无。批次阻塞：无；外层异常：无。整个批次墙钟1917.33s，含逐次输入检查、真实停止及归档。

每个启动尝试在调用前登记；首个无效、保护、未停稳、输入变化或归档错误后停止余项。正常TASK_FAILURE且有效停稳、无保护可以继续。异常后的应急尾段只请求零，原始记录独立标注。无补跑、无替换种子或点位。

## 保护、作用与解释边界

- warmup_x_neg_100_2026092709：保护事实 `{"simulation_valid": true, "invalid_reasons": [], "contact_reasons": [], "motion_reasons": [], "max_rotation_from_start_rad": 0.0009670621287921789, "checked_substeps": 54810}`；错误 `None`；离线审核 `True`。
- warmup_x_neg_100_2026092710：保护事实 `{"simulation_valid": true, "invalid_reasons": [], "contact_reasons": [], "motion_reasons": [], "max_rotation_from_start_rad": 0.0011788791759012182, "checked_substeps": 54420}`；错误 `None`；离线审核 `True`。
- warmup_x_pos_100_2026092709：保护事实 `{"simulation_valid": true, "invalid_reasons": [], "contact_reasons": [], "motion_reasons": [], "max_rotation_from_start_rad": 0.0014533985765428925, "checked_substeps": 62960}`；错误 `None`；离线审核 `True`。
- warmup_x_pos_100_2026092710：保护事实 `{"simulation_valid": true, "invalid_reasons": [], "contact_reasons": [], "motion_reasons": [], "max_rotation_from_start_rad": 0.0016963762261846304, "checked_substeps": 62680}`；错误 `None`；离线审核 `True`。
- warmup_y_neg_100_2026092709：保护事实 `{"simulation_valid": true, "invalid_reasons": [], "contact_reasons": [], "motion_reasons": [], "max_rotation_from_start_rad": 0.0013882963272696491, "checked_substeps": 58370}`；错误 `None`；离线审核 `True`。
- warmup_y_neg_100_2026092710：保护事实 `{"simulation_valid": true, "invalid_reasons": [], "contact_reasons": [], "motion_reasons": [], "max_rotation_from_start_rad": 0.0015227466895172128, "checked_substeps": 58300}`；错误 `None`；离线审核 `True`。
- warmup_y_pos_100_2026092709：保护事实 `{"simulation_valid": true, "invalid_reasons": [], "contact_reasons": [], "motion_reasons": [], "max_rotation_from_start_rad": 0.0019178137908716026, "checked_substeps": 67590}`；错误 `None`；离线审核 `True`。
- warmup_y_pos_100_2026092710：保护事实 `{"simulation_valid": true, "invalid_reasons": [], "contact_reasons": [], "motion_reasons": [], "max_rotation_from_start_rad": 0.001820879887993527, "checked_substeps": 67710}`；错误 `None`；离线审核 `True`。

“有效命令周期”指受限命令相对同状态零残差命令的改变量非零，不是实际位置改善或接触纠偏收益。绝对积分和带符号积分均保留在[机器结果](assessment.json)，防止把随机正负抵消误判为没有作用。同时间实际位置/姿态与旧零残差的差异也保留，但包含阶段及停止时刻差异，仅作描述。

四个旧零残差档案来自B2-06且已核验；本轮未新增零残差积分，也不要求随机动作后的轨迹前缀与零残差一致。物理、控制、奖励、保护、任务成功标准均未更改。native/256段刚性接触仍未作实物标定；离散四点和两随机流不覆盖连续初始域、非零倾角或学习后策略。

## 判据与验证

预检要求八回合全部计算有效、实际停稳、保护原因均空，并且每回合有接触和非零有效命令记录。当前结论：**通过候选预检**。即使通过，也只进入接触学习方案/准入版本审查，不自动启动SAC。

- 相关测试80项通过，随机序列与现有WarmupPolicy核对；新增反例及运行前审查见[实施记录](实施记录.md)。
- 872生产/配置输入和301旧封存文件逐次核验；正式运行前绑定协议和本包checks脚本，保留原代码版本。
- 逐周期复核动作序列、时间、观测、权限、屏蔽、命令合成与阶段覆盖后的执行值，包含停止/回撤及恢复后行；从原始停止样本复算停止门和末端稳定性。额外重建最初连续RUNNING段B2反馈，覆盖数另列，不冒称全回合B2状态重建。
- 新进程离线复算精确一致，见[复算收据](analysis/recheck.json)。无效或不完整记录保留错误，不冒称完整审核通过。

入口：[冻结协议](protocol.json)、[全尝试账](attempts.json)、[执行收据](execution.json)、[原始档案](runs/)、[清单](manifest.json)。项目独立Python用`-X utf8 -B`运行本包`checks/analyze.py --check`可离线核对；已有runs目录拒绝再次执行物理批次。

后续范围、准入版本及待审预算见[下一步决策](下一步决策.md)。本次交付后先汇报，尚未启动下一阶段。

![接触与最终误差](figures/01_preflight.png)
