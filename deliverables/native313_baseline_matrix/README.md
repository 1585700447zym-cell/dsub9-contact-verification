# 新版共同环境 B1/B2 七工况重评与训练准入

2026-09-23。**可进入残差接口实现；首次训练仍须接口验收。**

本轮在相同的独立 MuJoCo 3.13.0 native 环境完成14个固定开发回合，B1/B2各7个。未调控制参数，未改变几何、材料、质量、驱动和保护阈值，未训练SAC。正式3.9.0安装保留。

## 结果

| 方法 | 完整成功 | 实际停止后2s合格且末端仍稳 | 全回合严格安全与停止 | 候选有效记录 |
|---|---:|---:|---:|---:|
| B1 固定导纳 | 1/7 | 7/7 | 7/7 | 7/7 |
| B2 搜索与恢复 | 3/7 | 7/7 | 7/7 | 7/7 |

这是已经用于开发的七个工况，不是独立测试成功率。“候选有效记录”只表示本轮回合可用于接口设计依据，尚未提交任何SAC经验池；有效保护失败仍是失败，不能算安全成功。

| 工况 | 方法 | 原终止原因 | 最终类别 | 推进mm | XY误差μm | 峰值力mN | 最大穿透μm |
|---|---|---|---|---:|---:|---:|---:|
| aligned | B1 | GEOMETRIC_SUCCESS | FULL_SUCCESS | 3.991 | 0.00 | 0.000 | 0.000 |
| aligned | B2 | GEOMETRIC_SUCCESS | FULL_SUCCESS | 3.991 | 0.00 | 0.000 | 0.000 |
| x_offset_pos_100um | B1 | NO_PROGRESS | VALID_TASK_FAILURE | 0.250 | 99.99 | 24.474 | 7.136 |
| x_offset_pos_100um | B2 | GEOMETRIC_SUCCESS | FULL_SUCCESS | 3.990 | 9.63 | 24.474 | 7.136 |
| y_offset_neg_100um | B1 | NO_PROGRESS | VALID_TASK_FAILURE | 0.250 | 100.00 | 24.474 | 7.139 |
| y_offset_neg_100um | B2 | GEOMETRIC_SUCCESS | FULL_SUCCESS | 3.991 | 32.52 | 24.474 | 7.139 |
| roll_pos_1.5deg | B1 | NO_PROGRESS | VALID_TASK_FAILURE | 0.250 | 104.10 | 24.763 | 6.586 |
| roll_pos_1.5deg | B2 | TARGET_POSE_NOT_SETTLED | VALID_TASK_FAILURE | 3.991 | 80.17 | 24.463 | 6.586 |
| combined_a_scale_0.75 | B1 | NO_PROGRESS | VALID_TASK_FAILURE | 0.250 | 112.94 | 24.569 | 7.075 |
| combined_a_scale_0.75 | B2 | TARGET_POSE_NOT_SETTLED | VALID_TASK_FAILURE | 3.992 | 64.26 | 24.569 | 7.075 |
| combined_b_scale_0.75 | B1 | NO_PROGRESS | VALID_TASK_FAILURE | 0.250 | 111.98 | 24.474 | 6.985 |
| combined_b_scale_0.75 | B2 | TARGET_POSE_NOT_SETTLED | VALID_TASK_FAILURE | 3.991 | 52.38 | 24.463 | 6.985 |
| combined_a | B1 | NO_PROGRESS | VALID_TASK_FAILURE | 0.250 | 148.90 | 24.473 | 5.951 |
| combined_a | B2 | TARGET_POSE_NOT_SETTLED | VALID_TASK_FAILURE | 3.991 | 75.58 | 24.455 | 5.951 |

## 怎样读失败

FULL_SUCCESS：原回合成功，额外停止审计也通过。VALID_TASK_FAILURE：有效计算和停稳，但任务未完成。VALID_GUARD_FAILURE：触发保护并有效停止的失败，不能说全回合安全指标通过。STOP_NOT_QUALIFIED：停止验收未过，阻塞当前共同环境准入。INVALID_SIMULATION：数值/状态无效，不能作为正常学习经验。UNEXPLAINED_SAFETY_FAILURE：安全峰值未过且缺少对应保护证据，需要核查。

原回合动作预算均为20s，原最终判定观察为1s，保留原先提前结束规则；额外停止审计不重新给失败回合成功机会。停止计时按实际STOPPING事件，不按可能更晚的恢复失败决定时间。原首版audit和物理日志保留，最终报告独立重算；见[计时与归档说明](停止计时与异常归档补充.md)。

## 准入结论与下一步

本矩阵未发现上述共享数值/停止阻塞，可进入普通四维残差SAC接口实现。保留B1为简单对照、原B2为搜索恢复基线；不再追加传统控制参数扫描。该结论不等于连续训练分布已完整验证，更不等于已经开始训练。

下一能力统一完成reset/step、四维残差叠加、共享守卫、观测与奖励、无效经验隔离、保存加载和固定评价。先验证零残差逐周期复现新版B2，以及小范围XY训练分布初始化；通过后才首次短训。联合偏差扩展和独立测试仍在后续阶段。

## 文件与复现

- [机器可读结论](report_v1/assessment.json)：完整比较、实际停止计时和准入理由。
- [七工况对比图](report_v1/01_七工况方法对照.png)、[预定X/Y真实轨迹](report_v1/02_代表工况真实轨迹.png)、[月报讲解](月报讲解.md)。
- [环境与基线冻结记录](冻结依据.json)、[训练合同v2](训练合同_v2.md)、[数据划分引用](数据划分引用.json)。原32验证/64独立测试清单保留，本轮没有运行这些测试集。
- `b1_v1/`、`b2_v1/`：每工况原回合original.json.gz、stop_extension.json.gz、首版audit.json和源码快照；完整保留失败。

代码关系：模型生成→native候选环境→原B1或B2控制器→原回合运行器→追加停止采样→独立审计/报告。新增入口不改变控制器内部行为。

在VS Code打开工作目录 `D:\dsub9项目计划\first_stage_sim\.worktrees\dsub9-v1-contact-validation`。复现使用修正版v2和新的tag：

```powershell
& 'D:\KEYANRUJIAN\python.exe' -X utf8 -B -m tools.validation.run_native313_matrix_v2 --policy b1 --tag b1_reproduce_01 --package-path tmp/mujoco_3_13_probe
& 'D:\KEYANRUJIAN\python.exe' -X utf8 -B -m tools.validation.run_native313_matrix_v2 --policy b2 --tag b2_reproduce_01 --package-path tmp/mujoco_3_13_probe
```

要求使用已验收的同一路径与DLL；文件夹已经存在则拒绝覆盖。v2仅修正真实停止计时和NaN/Inf证据归档。本轮14回合来自保留的首版入口，最终停止判定已按v2语义独立复核；没有为v2额外重复14回合。修正版有边界测试，不能把它说成已做第二轮完整矩阵验证。

图由真实记录生成；没有制作或验收新的交互回放窗口。原SolidWorks/SDF资产、正式Python环境、VS Code设置和历史实验均保留。

本轮14回合均未实际触发回撤（recovery_count=0）。因此不把本矩阵说成已经验证新版全部恢复分支；条件回撤与残差屏蔽的专项检查纳入下一项接口验收。
