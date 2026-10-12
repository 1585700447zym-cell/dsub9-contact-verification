# 137D学习链和有限pilot整阶段审查

工作目录：D:\dsub9项目计划\first_stage_sim\.worktrees\dsub9-v1-contact-validation；原脏分支feature/dsub9-dynamic-actuator-v1，不改已有内容，不提交、不创建工作树。

新增实现：tools/learning/v4_pilot_contract.py、v4_replay.py、v4_sac.py、v4_pilot_chain.py、v4_checkpoint.py、tools/validation/run_v4_learning_pilot.py。
新检查：tests/learning/test_v4_learning.py、test_v4_checkpoint.py；tests/task_variants/test_v4_learning_pilot.py。

计划docs/superpowers/plans/2026-10-06-v4-learning-pilot.md；规格docs/stage_b/论文对照协议_v4.md、训练合同_v3.md。
Ruling记录本目录progress.md。当前尚无新动力学/正式更新；实测需资格证据绑定后才允许。前序PC03单脉冲动态通过，有效连续性证明有限，不能假称普遍策略安全。

Review Focus（原计划）：
- schema/权限是否同周期；actor与温度inactive是否连Adam动量/计数也跳过，critic目标下一动作/熵屏蔽是否一致；17新增字段真正进入网络。
- 生效动作、原请求和经验动作、周期峰值奖励、尾段终止/精确标签是否保持；无效数据/评价样本是否误入池。
- 完整检查点是否含实际原始归档、所有优化/RNG/回放/信用、历史；恢复前是否验证绑定/形状/Adam计数和全部数据，不能把旧120维恢复成功当准入。
- 动态领取/STOP/错误关闭、正式更新尝试记账、分支硬保护后另一分支继续是否公平；初始化/保存/读取失败是否保留并禁止重试。
- 固定评价是否使用同共同模型/B2/裁判、完全冻结末次检查点，独立复现是否逐轨迹相同；未执行/停止分支不能被当作被另一组击败。

只读审查，禁止执行物理仿真、正式训练或再派subagent。可读文件与离线纯数值测试。返回Critical/Important/Minor、文件行号、实际触发条件、修复建议、Declined to judge。对于规格未列输入，按合理使用期望/实际影响分级。保留失败而不越预算是要求。
