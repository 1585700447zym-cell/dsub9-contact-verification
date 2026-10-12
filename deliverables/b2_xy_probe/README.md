# B2-5.3 短时暂停额外横向搜索

2026-09-22。X +100 μm 单次新动力学试验完成。预定暂停最多 1 s；实际 0.726 s 后即满足原 V2 退出资格，正常插入到 3.991 mm。XY 误差 63.979 μm 超过原定 50 μm，仍未完整达标。

先看 [单变量试验报告](comparison_first_frozen_x100/B2-5.3单变量试验报告.md)、[月报小结](月报小结.md)、[月报图](comparison_first_frozen_x100/01_月报单变量对照.png)。[真实轨迹 GIF](comparison_first_frozen_x100/真实轨迹回放.gif) 来自本次积分记录，含停止后的状态，不是预设插入动画。

## 本项说明了什么

与失败 V2 相比，在保留更严格退出资格的同时恢复了该例插入深度。前 5388 个采样与 V2 一致，363 条干预搜索命令核对通过。0.6 s 窗口内双方仍处于 SEARCH；1.0 s 和整回合结果包含候选随后进入 INSERT 的总效果。

该结果没有超过旧 B2 的终点精度，也没有证明其他工况改善。0.1 s 搜索恢复坡道没有在此回合实际触发，仅有单元测试覆盖。保留旧基线，候选尚不进入 SAC 训练。

## 文件怎样连接

- [控制器](../../tools/control/search_probe.py)：继承原 V2，仅给额外 XY 搜索项增加预定增益窗口。
- [实验入口](../../tools/validation/run_b2_xy_probe.py)：核验旧 V2，创建同一环境并运行 X 一例，保存日志。
- [报告入口](../../tools/reporting/report_b2_xy_probe.py)：只读记录，审计命令与退出资格，生成图和回放。
- [预先冻结的协议](first_frozen_x100/实验协议.md)：每次运行保存自己的副本。
- [完整运行索引](first_frozen_x100/results_index.json)、[完整轨迹](first_frozen_x100/runs/x_offset_pos_100um_xy_probe.json.gz)、[原始审计](comparison_first_frozen_x100/comparison_audit.json)。

## 在现有窗口看这一例

VS Code 的 05 仍运行旧 V2；要查看新例，请用 06“回放自己保存的记录”，粘贴：

`D:\dsub9项目计划\first_stage_sim\.worktrees\dsub9-v1-contact-validation\deliverables\b2_xy_probe\first_frozen_x100\runs\x_offset_pos_100um_xy_probe.json.gz`

这是保存结果的回放。重新计算本例和新报告的命令见单变量报告末尾，必须用新的输出 tag；当前 GUI 没有新增本候选的实时菜单。

## 下一细分

保持候选参数不变，扩展到 Y −100 μm 一例，与原 V2 的 Y 记录比较，检验收益是否只在 X 出现，并观察能否覆盖暂停后的恢复分支；不要为了触发分支而改变正式工况或挑选结果。该扩展本轮未运行，先向用户汇报当前结果。
