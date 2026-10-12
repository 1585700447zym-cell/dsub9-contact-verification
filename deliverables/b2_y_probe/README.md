# B2-5.4 Y 工况同参数检验

2026-09-22。本项完成一例 Y −100 μm 新动力学试验。冻结 X 暂停策略未为 Y 改参数：最终推进 0.202 mm，原 V2 为 0.217 mm；仍未插入到位，因搜索预算耗尽停止。姿态误差由 0.669° 增为 1.129°。

先看 [完整报告](comparison_first_frozen_y100/B2-5.4同参数Y工况报告.md)、[月报小结](月报小结.md)、[月报对照图](comparison_first_frozen_y100/01_月报Y工况对照.png)、[真实轨迹回放](comparison_first_frozen_y100/真实轨迹回放.gif)。

## 当前结论

同一策略在 X 恢复深度，在 Y 未恢复深度；两例均未完整达标，不能将 X 的结果推广为通用改进。本例实际覆盖了暂停后的平滑恢复：零增益命令 1.002 s，10.046 s 触发，11.146 s 恢复完整额外搜索。3668 条命令与原始轨迹核对通过。

暂停不增加搜索预算。本例动作在 17.382 s 因搜索预算耗尽停止，随后保留 1 s 停止观察；不是耗尽 20 s 全局动作时限。

## 代码、配置和数据怎样连接

| 环节 | 文件 | 作用 |
|---|---|---|
| 实验入口 | [run_b2_y_probe.py](../../tools/validation/run_b2_y_probe.py) | 校验冻结 X 与原 V2 Y，选择 Y 初始条件，创建同一环境并调用原动力学执行流程 |
| 复用控制器 | [search_probe.py](../../tools/control/search_probe.py) | 相对原 V2 只调节额外 XY 搜索增益；X/Y 共用且未修改 |
| 运行配置与来源 | [运行索引](first_frozen_y100/results_index.json) | 保存工况、控制器配置、来源路径及校验值 |
| 冻结输入 | [协议](first_frozen_y100/实验协议.md)、[源码快照目录](first_frozen_y100/source_snapshot/) | 保留该次运行实际使用的实现和规则 |
| 动力学输出 | [完整轨迹](first_frozen_y100/runs/y_offset_neg_100um_xy_probe.json.gz) | 每 2 ms 的状态、命令及干预记录；峰值覆盖物理子步 |
| 分析和展示 | [report_b2_y_probe.py](../../tools/reporting/report_b2_y_probe.py) | 只读历史记录，复核命令、生成图和实际位姿回放，不重跑动力学 |

新建 Y 入口是为了保留已冻结的 X 实验实现；控制器没有复制或另行调参。重新运行命令见完整报告末尾，使用新 tag 保留所有尝试。

## VS Code 与 MuJoCo 中查看

使用 06“回放自己保存的记录”，输入：

`D:\dsub9项目计划\first_stage_sim\.worktrees\dsub9-v1-contact-validation\deliverables\b2_y_probe\first_frozen_y100\runs\y_offset_neg_100um_xy_probe.json.gz`

这是已计算结果的回放；05 仍运行原 V2。本次没有改变已有菜单。

## 验证与边界

本次入口/报告及复用控制器的 22 项相关检查通过。全仓库测试 382 项通过、23 项 SDF 构建检查因 Windows SDK 目录访问受限失败，详见 [测试记录](test_status.json)。不能宣称全仓库全通过；该限制与本次使用的 256 段凸碰撞动力学路径不同。原 SDF 源码和插件指纹未改变。

## 下一细分

对已保存 X/Y 轨迹做离线受阻诊断：比较暂停触发时的横向位置、倾斜、各针接触和受力，以及暂停/恢复后的变化，定位 Y 仍卡住而 X 能推进的差异。先输出证据与单一可检验的改动建议，不立即扫参数或训练。该诊断本轮未开展，本项完成后先汇报。
