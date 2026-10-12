# 入口接触一致性候选：静态通过，动态复验未通过

2026-09-22。**当前仍是能力 A 的仿真可靠性与训练准入环节。候选 native_tight_v1 不予采用：一个步长下完成插入并停稳，另一步长下出现可复现的异常穿透。正式修复尚未达成，B1/B2 新环境矩阵和学习训练均未启动。**

## 本轮做成了什么

建立了独立候选环境和回归工具，把两类历史异常放在同一套检查中。候选使用 native CCD，检测容差为 1e-12；模型几何、孔分段、质量惯量、材料、驱动、控制器和保护阈值不变。旧 MPR 环境和实验结果保留，候选没有接入默认运行入口。

先导对照共有 15 次静态检查。仅增加 native 迭代次数或关闭多点接触不能解决历史异常；收紧容差的候选在旧 128/256 段异常姿态及近期停止疑点姿态均得到浅接触结果。因此只验证这一候选，没有继续扫描参数。

候选随后通过了本轮固定的 708 个静态姿态检查：63 个入口邻域、501 个旧停止轨迹姿态、140 个历史姿态以及 4 个明确分离/孔壁状态。应区分：501 个姿态中实际只有 80 个检测到接触，140 个历史姿态中只有 24 个带 >1 μm 几何正见证。侧壁检查另逐针核验了 9 个对应针孔配对，不能把任意一处接触当作全部覆盖。

静态结果支持这组已测姿态的几何一致性，不能证明所有姿态或整个动力学过程可靠。

## 完整动力学给出了否决证据

控制器沿用原 B2 Y 配置，从原初始条件运行完整闭环；停止最多观察到命令发出后 2 s。不是只把上一回合最后一帧改掉。

| 项目 | 物理步 0.2 ms | 物理步 0.1 ms |
|---|---:|---:|
| 原回合结果 | GEOMETRIC_SUCCESS | INVALID_PENETRATION |
| 关键时刻 | 9.650 s 发出最终停止 | 2.4316 s 无效终止 |
| 最终停止后 2 s 复验 | 通过 | 未进入最终停止，不具备验收条件 |
| 全回合最大穿透 | 7.016 μm | 223.602 μm |
| 峰值合力 | 24.474 mN | 24.474 mN |
| 原回合墙钟耗时（同机并行运行） | 327.45 s | 290.52 s |

0.2 ms 回合按当前几何完成标准达标，最后 0.1 s 的全部 501 个物理步采样线/角速度均满足原停止门槛。**这只是一条候选成功轨迹，不能计入正式基线成绩或用于宣称可靠成功率。** 0.1 ms 回合被保护正确终止，不能把保护终止当成正常搜索失败。

两条轨迹在共同覆盖至 2.430 s 的范围内，最大位置差仅 0.106 μm；之后 0.1 ms 在 2.4316 s 出现异常。报告仅配对真实共同采样时刻，保留未配对的末物理步和较长回合剩余数据，不外推、不删掉失败。完整回合的事件序列不同，时间步一致性未通过；即使前段位姿很接近、合力峰值接近，也不能绕过这一失败。

## 新反例已冻结并重现

对 0.1 ms 失败回合的实际终止位姿，在同一候选配置下做一次独立静态前向，仍返回 **223.602245 μm** 的最大深度。涉事几何对为 `pin_06 / hole_convex256_06_main_218`。

该对几何的轴向分离位移上界约 **0.000379 μm**。该上界不是任意接触法向深度的真值，但结合浅接触、很小的相邻位姿变化及同姿态重现，足以否决本候选的当前可靠性要求。更严格的容差只修复了原有几个样例，没有提供全局保证；底层数值退化的确切代码路径还未定位。

MuJoCo 3.9.0 的原生凸碰撞实现包含受检测容差影响的 GJK/EPA 路径，本项目观察到的容差敏感性不能直接归因到某一源码分支，仍需要最小复现分析。[对应版本官方源码](https://github.com/google-deepmind/mujoco/blob/3.9.0/src/engine/engine_collision_gjk.c)。

## 接下来应做什么

这是需要先汇报的困难节点。建议下一项完整交付改为 **“新异常的最小复现与碰撞修复可行性判定”**：

1. 从新失败姿态提取涉事针圆柱和单个孔凸块，保持实际编译几何及变换，验证能否在最小场景稳定重现。最小化改变了浮点运算时可能不再重现，这本身也要记录。
2. 对浅接触的距离、法向和有限微扰响应建立独立核查，定位问题属于距离求解、几何数值条件还是接触点生成。不要继续凭完整插入是否成功调检测容差。
3. 给出具体的修复选择及成本，再决定是否升级/修补碰撞实现或改变几何表示；不在原因未明时直接自定义整套碰撞器或换引擎。
4. 修复后必须包含本轮新反例在内重新跑静态回归和两步长全回合；两者通过才进行同环境 B1/B2 七工况重评。

本轮按已登记的预算完成两次动力学回合，失败后没有追加参数试验。研究路线仍是学习型装配；暂缓的是仿真环境准入。仿真异常不能当作传统控制方法能力不足的论文证据。

## 文件和代码之间的关系

- `tools/dynamics/contact_candidate.py`：独立候选环境，继承现有 CartesianEnvironment，只改变接触后端和检测容差。
- `tools/validation/probe_contact_backends.py`：15 次先导选项对照，仅用于诊断。
- `tools/validation/validate_contact_candidate.py`：708 个静态姿态回归；[完整结果](static_gate_v1/results.json)。
- `tools/validation/audit_contact_candidate.py`：对已保存结果严格核验 9 对侧壁接触；[补充审查](strict_static_audit.json)。
- `tools/validation/run_contact_candidate_stop.py`：调用原 B2 控制器执行完整回合，逐物理步记录 STOPPING 速度，保存保护事件和源码快照。
- `tools/reporting/report_contact_candidate.py`：只读结果、按共同时间对齐、输出拒绝判定和图；[机器可读结论](report_v1/assessment.json)。
- [新失败姿态](新增失败冻结姿态.json)、[核心依赖追溯](核心依赖追溯核查.json)、[月报讲解](月报讲解.md)、[独立复核记录](独立复核记录.md)。

动力学数据分别在 [0.2 ms 目录](stop_dt0p2_v1/) 和 [0.1 ms 目录](stop_dt0p1_v1/)；`original_duration.json.gz` 是原回合，`stop_extension.json.gz` 是后续观察和物理步停止速度。失败回合没有最终停止，后者并不代表已完成停止复验。

## 在 VS Code 中复现

在当前工作树打开集成终端，使用下面入口。所有参数和拒绝结果均保留；这是开发诊断，尚未加入默认 01～06 菜单。新增 tag 必须不存在，重复时改名。

```powershell
Set-Location 'D:\dsub9项目计划\first_stage_sim\.worktrees\dsub9-v1-contact-validation'
# 先核验交付与全部保护输入；PASS 只表示文件一致，不表示候选物理合格
& 'D:\KEYANRUJIAN\python.exe' -X utf8 -B -m tools.validation.verify_contact_candidate_delivery
# 无动力学积分：重复静态回归，原结果不覆盖
& 'D:\KEYANRUJIAN\python.exe' -X utf8 -B -m tools.validation.validate_contact_candidate --tag my_static_check
# 两条完整动力学重跑，分别保存成功候选与失败证据；预计需要数分钟
& 'D:\KEYANRUJIAN\python.exe' -X utf8 -B -m tools.validation.run_contact_candidate_stop --tag my_stop_02 --timestep 0.0002
& 'D:\KEYANRUJIAN\python.exe' -X utf8 -B -m tools.validation.run_contact_candidate_stop --tag my_stop_01 --timestep 0.0001
# 只重画已交付的冻结结果，不会自动读取上面 my_* 的新回合
& 'D:\KEYANRUJIAN\python.exe' -X utf8 -B -m tools.reporting.report_contact_candidate --output-dir deliverables/contact_consistency_repair/my_report
```

静态脚本的 4 个核心依赖由补充追溯文件核对，旧静态结果未追改。重跑前若代码、模型或历史文件已改，应先停止核对版本。当前候选不适合训练；复现失败是预期结果，不能因程序正常退出就解释成物理验收成功。
