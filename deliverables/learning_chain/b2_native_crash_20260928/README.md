# 原生碰撞崩溃诊断与容量修复

2026-09-28，按用户“继续排查原因解决问题”执行。**已定位原生崩溃根因，容量修复通过故障现场与原故障完整回合验证。** 尚未恢复训练或授予新运行库的正式训练资格。机器复核见 [assessment.json](assessment.json)，独立审查见 [review.md](review.md)。

- 精确触发：第1894控制周期、3.7879999999996157秒；调用前积分状态有限，警告0；原DLL偏移0x44faf发生访问违规。
- `model.mjb` 与 `capture_02/pre_forward_state.npy` 支持全新进程单次 `mj_forward` 复现，无需训练和物理积分。
- 1077候选二分到第7针 `pin_07` 与孔壁分块 `hole_convex256_07_main_233`，单对仍复现。
- 原版低层碰撞算法的缓冲区哨兵实测越界4字节；带边界检查副本在第25项、已分配24项时退出，nfaces99、nverts31。
- 修复仅把两组horizon数组的分配和布局偏移统一改为18×迭代上限：最多6N个三角面、每面至多3条边。完整图形/物理模型和规则不改。
- 容量修复单对验证：越界0；距离−2.3561768402525625e−7米、GJK13、EPA35，与原版独立缓冲区计算一致。原版已发生未定义行为，这些相同数值仅作辅助观察，不能证明全部接触结果或轨迹等价。

证据：`capture_02/pre_forward.json`、`capture_02/native_exception.json`、`replay_forward_01_exit.json`、`isolated_pairs.json`、`canary_original.log`、`canary_guard.log`、`canary_fixed.log`；修复脚本 `patch_horizon.py`，上游固定提交 `123347c0eeab7e13c8da0828ab593bbd95bcf335`。

## 已完成的验证

| 验证 | 未修复 | 容量修复 |
|---|---|---|
| 独立缓冲区哨兵 | 越界4字节；检查版在第25项退出 | 越界0 |
| 捕获状态、全新进程单次完整forward | 官方DLL访问违规 | 正常返回，687接触，状态有限，7项警告均0 |
| 同编译环境完整DLL对照 | `control_forward_02` 仍访问违规 | `fixed_forward_01` 通过 |
| 同工况、同种子、同PCG动作流完整回合 | `capture_02` 第1894周期崩溃 | `fixed_episode_01` 完成6311周期/63110子步，完整成功、有效且真实停稳，无保护违规 |

完整回合执行与归档307.58秒；原始记录 [episode.json.gz](fixed_episode_01/episode.json.gz)，结果 [completed.json](fixed_episode_01/completed.json)。离线复核逐周期重建全部请求动作、核对归档摘要、复算实际停止与任务分类，并检查原冻结输入。这里的成功来自随机预热诊断，不是训练后策略成功率或学习收益。

第一次本地对照 `control_forward_01` 无效：源文件复制保留旧时间戳，增量构建跳过，该DLL与修复版摘要相同。已保留记录；更新时间戳后确实重新编译的 `control_forward_02` 才计为未修复对照。另一次最早的诊断脚本在任何物理初始化之前因API名称错误退出，也原样保留。

## 修复交付与边界

修复只有两处分配大小和一处数组偏移，不改几何、接触阈值、控制、奖励或采样。固定MuJoCo 3.13.0提交 `123347c0eeab7e13c8da0828ab593bbd95bcf335`，容量上界及布局一致性经独立审查，无Critical/Important阻断项。完整构建使用本机MSVC19.51、Release/x64；候选包全部文件摘要见 [horizon_fixed_runtime.json](horizon_fixed_runtime.json)，构建与保存的DLL见 [build.json](build.json)。

- 修复DLL SHA256：`4007b6b0956eabc1a3892ac3c3f0947d0e98b90a0604cd8ffcbb795227274047`。
- 同编译环境未修复对照DLL：`29114119aa437c242135eb74f7eb47498a847e03f824c119ef90f52435213d2b`。
- 原官方DLL保持：`5a4bcda24e9ada75e6f787e810e163fb25739ec1c5e62083af96286d26cfcb48`。

原冻结890输入、84历史文件、25重试绑定文件、旧初始检查点及原运行库全部校验保持。本项新增2次诊断动态启动（1次故障复现、1次修复验证），连同旧原运行/重试6次为8次；静态调用和物理前设置失败单列。新增SAC优化0、经验发布0。归档内 `valid_for_learning` 是原物理审核函数的条件判定；顶层 `training_admitted=false`，诊断数据不能据此入池。

已证明当前捕获崩溃的因果修复与原故障工况完整运行；不证明整个引擎/任意轨迹均无缺陷，也不证明新编译DLL与旧DLL全部轨迹精确等价。B.2整体尚未完成，原训练与一次重试继续封存为失败，自动跟踪保持暂停。

## 下一项

为修复版建立严格的新运行库资格，绑定路径/版本/完整摘要，补错配拒绝验证；保留旧资格。核对新资格下的零更新学习状态与旧初始状态，明确旧四点评价属于旧DLL并处理共同版本评价，再恢复原有限训练方案。当前诊断用的进程内依赖替换不能用于正式训练。无需另开算法、奖励或参数探索。

离线重复核验（不运行物理或优化）：

```powershell
./tmp/learning_cpu_20260924/Scripts/python.exe -X utf8 -B deliverables/learning_chain/b2_native_crash_20260928/verify_repair.py
```

`validate_candidate.py` 的动态/静态重放入口必须使用新输出名；禁止覆盖本次证据。构建目录最后一次产物属于未修复对照，使用候选必须按上述包路径和SHA核对，不能直接拿构建目录中的DLL替换正式运行库。
