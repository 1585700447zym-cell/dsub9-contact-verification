# B.1阶段内交付｜隔离学习环境、张量权限与未训练策略验证

日期：2026-09-24。对应[交付总览](../../../项目交付总览.md)的B1-04。该增量不改变共同物理、保护阈值、奖励或经验准入；**不是B.1整体验收，不是SAC训练成果。** 月报统一更新[本月滚动素材](../../monthly_progress/2026-09/月报素材_2026-09.md)，不另建阶段月报。

## 获得的能力

- 原解释器的用户级PyTorch导入错误再次复现；在项目内新建不继承系统/用户site-packages的虚拟环境，同版本`torch2.12.1+cpu`能实际导入、张量反向传播及调用SB3策略网络。原环境未修复、删除或覆盖。
- [张量权限原语](../../../tools/learning/tensor_masks.py)补上NumPy参照缺少的自动微分语义：inactive动作归零、critic下一状态无虚构熵项、终止不bootstrap、actor不更新温度、温度不反传到actor、只对active行取均值。
- 全inactive时不调用优化器step，已有Adam动量和步数不变；非有限loss/gradient在参数更新前拒绝。这只是单优化器原语，不是多网络原子事务或完整SAC训练器。
- 未训练SB3 SACPolicy在现有120维观测/四维动作接口上可保存加载。两次固定同轴开发短轨迹（各8个控制周期，随后独立停止审核）逐项相同；所有经验仍隔离。网络诊断结构`[32,32]`和种子20260924不作为训练超参数冻结。

## 验证与边界

新增18项张量测试先因缺少实现失败，随后全部通过；两个SB3/仿真边界资格测试通过。独立审查再补两项梯度链反例，最终专项为22项通过。旧143项接口基线在改动前重跑通过；新环境修正反例后完整目录**165/165通过**，已包含22项专项。完整复验及失败处置见[验收记录](验收记录.md)、[机器结论](assessment.json)。

- 张量反例只在人工标量上执行Adam检查；真实SB3 actor/critic仅作前向、反向和保存加载，优化器状态为空。没有调用`SAC.learn`、没有用仿真经验做学习更新。
- 短轨迹不是完整装配评价，不计成功率，不替代七工况回归。旧809项动态输入指纹核对用于证明物理/控制实现未变，不是本轮重跑七工况。
- CPU仅用于隔离依赖和正确性检查；没有比较GPU，也未冻结正式训练设备或成本预算。
- 原用户级CPU包目录残留CUDA DLL的推断得到“干净同版本CPU包可运行”的支持，但没有证明这是原目录故障的唯一根因。原错误与旧阻塞报告原样保留。
- 完整SAC采集器、整回合审核后的经验池发布、学习循环及多网络更新、完整策略/优化器恢复仍未实现。不能把本模块直接接到通用SB3 rollout并绕过回合隔离。
- 姿态/探索范围尚未冻结，`training_admitted=false`。未使用独立测试案例、未引入机器人或夹爪。

## 运行入口

从现有工作目录执行，不用原`D:\KEYANRUJIAN\python.exe`直接运行新增张量测试（其用户级torch仍导入失败）：

```powershell
Set-Location 'D:\dsub9项目计划\first_stage_sim\.worktrees\dsub9-v1-contact-validation'
$env:MPLCONFIGDIR = 'D:\dsub9项目计划\first_stage_sim\.worktrees\dsub9-v1-contact-validation\tmp\learning_mpl_cache'
& '.\tmp\learning_cpu_20260924\Scripts\python.exe' -X utf8 -B -m pytest -p no:cacheprovider -q tests/learning
& '.\tmp\learning_cpu_20260924\Scripts\python.exe' -I -X utf8 -B -m pip check
& 'D:\KEYANRUJIAN\python.exe' -X utf8 -B -m tools.validation.verify_native313_matrix_delivery
```

MPLCONFIGDIR仅指定该进程的本地绘图缓存，避免SB3间接导入matplotlib时尝试写用户目录；不改全局设置。无GUI、无训练。

## 重建依赖

[环境记录](environment.json)给出解释器、包路径、版本、torch RECORD/9个DLL摘要及已有MuJoCo3.13指纹；[固定依赖](requirements.lock.txt)列出本次所有37个发行包。既有隔离MuJoCo目录仍由`verify_runtime`选择，不在新环境安装另一份MuJoCo。

如需重建，选择一个**不存在的新目录**，不要覆盖本次已验证环境；以下仅为复现说明，联网安装仍按权限流程执行：

```powershell
& 'D:\KEYANRUJIAN\python.exe' -X utf8 -B -m venv 'tmp/learning_cpu_rebuild_NEW_TAG'
& 'tmp/learning_cpu_rebuild_NEW_TAG/Scripts/python.exe' -I -B -m pip --isolated install --index-url https://download.pytorch.org/whl/cpu 'torch==2.12.1+cpu' --only-binary=:all:
& 'tmp/learning_cpu_rebuild_NEW_TAG/Scripts/python.exe' -I -B -m pip --isolated install --index-url https://pypi.org/simple -r 'deliverables/residual_interface/learning_tensor_20260924/requirements.lock.txt' --only-binary=:all:
& 'tmp/learning_cpu_rebuild_NEW_TAG/Scripts/python.exe' -I -B -m pip check
```

依赖版本锁定不等于离线安装包已交付；网络源仍需可用。复建后必须重跑实际导入、张量、策略边界与接口测试，不只比较版本字符串。本次使用官方[PyTorch安装指南](https://pytorch.org/get-started/locally/)及官方CPU包索引查询可用包；选固定2.12.1版本而非自动升级最新版本。

## 后续交付

继续B.1：落实真正的SAC采集/经验发布适配，再补姿态/探索范围与采样、更新成本等准入证据。当前总状态和顺序以[项目进度跟踪](../../../项目进度跟踪.md)为准；本归档保留本次时点。
