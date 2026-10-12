# 独立新版环境的完整回归与停止验收

2026-09-22。本项能力完成：**MuJoCo 3.13.0 的独立 native 候选通过本轮静态回归、两个完整 B2 Y 回合的安全/停止检查及预先登记的步长比较，可以进入共同环境下 B1/B2 七工况重评。** 正式环境仍为 3.9.0，训练尚未准入。

## 这次解决了什么

上一版在 0.1 ms 回合出现 223.6 μm 异常穿透，不能作为可信学习环境。这次沿用同一几何、材料、惯性、驱动、控制器配置和保护阈值，只在独立进程使用 3.13.0、native 接触和 1e-12 容差。两个完整回合均未重现该严重异常，并完成几何插入和持续停稳。

这意味着当前固定 Y 工况的阻塞有了可用候选解法，不代表所有工况、SDF 插件、真实夹持、CR5 或实机均已验证。也不把一次开发检查当作论文成功率。

## 结果

| 检查 | 结果 |
|---|---|
| 有效设置与模型兼容 | 29 个公开选项、19 组模型数组、动态配置已记录；唯一选项差异为休眠阈值，两版均未开启休眠 |
| 历史静态回归 | 708 项通过；140 个见证姿态中有 24 个明确正见证，未漏对应针孔 |
| 新异常及邻域 | 23 个邻域姿态＋1 个九针主孔正检查通过；不是靠所有接触消失获得通过 |
| 静态合计 | 732 项通过 |
| 0.2 ms 完整回合 | GEOMETRIC_SUCCESS；最终停止时刻 9.708 s，观察至 11.708 s；持续停稳通过 |
| 0.1 ms 完整回合 | GEOMETRIC_SUCCESS；最终停止时刻 9.688 s，观察至 11.688 s；持续停稳通过 |
| 共同末端位置 / 姿态差 | 3.463 μm / 0.000289°，通过原门槛 20 μm / 0.1° |
| 共同轨迹最大位置差 | 25.980 μm；如实保留，不声称整条路径误差均低于 20 μm |
| 峰值力相对差 / 事件序列 | 约 0.000167% / 相同，通过原比较门槛 |

| 全回合峰值 | 0.2 ms | 0.1 ms | 原安全门槛 |
|---|---:|---:|---:|
| 接触合力 | 24.474283 mN | 24.474242 mN | <25 mN |
| 夹持点接触力矩 | 0.149895 mN·m | 0.155680 mN·m | <0.5 mN·m |
| 最大穿透 | 7.138923 μm | 7.130237 μm | <30 μm |

最终停止后每个物理步均有速度记录（分别 10000 / 20000 个）；最后连续 0.1 s 满足线速度≤10 μm/s、角速度≤0.001 rad/s。合力峰值接近原保护上限，不能据此声称具有很大的安全裕量。

两个回合总长度不同：按 2 ms 采样对齐，共有 5845 个共同时间点，较长回合余下 10 个点保留、不外推另一回合。此处是固定反馈回合的步长敏感性检查，不是全局数值收敛证明。

休眠阈值变化的判读依据为本地有效选项 enableflags=0，以及[MuJoCo 官方休眠说明](https://mujoco.readthedocs.io/en/latest/XMLreference.html#option-flag-sleep)。除已检查内容外，不宣称引擎内部实现等价。

## 原始 ERROR 与物理结果的区别

本轮首次入口复用了旧运行器，发生一处归档错误：它把新协议的哈希写在旧协议路径键下。错误发生在完整回合和停止延续数据已经保存之后。**两个原始 results_index.json 的 ERROR 状态原样保留，没有改成 COMPLETE。**

独立审核工具只接受这个精确错误；核对所有其他保护输入、历史资产、隔离 DLL、静态递归依赖、原回合与延续首尾连续性，以及异常保存轨迹与完整轨迹逐条一致性，再用原判据重算停止结果。结论保存在各目录的 audited_results.json。归档适配另存为新复现入口，不改旧物理主循环。这两次是完整物理数据通过审核，不是首次运行器无错误完成。

## 文件怎样串联

1. `tools/model/contact_development.py` 生成针孔接触模型，原 SolidWorks/SDF 资料仍保留。
2. `tools/dynamics/contact_candidate.py` 创建原 native_tight_v1 候选，固定容差；本轮只改变加载的 MuJoCo 版本。
3. `tools/validation/validate_contact_candidate.py` 执行冻结姿态和接触见证检查，新版入口再补充新增异常邻域。
4. `tools/control/search_recovery.py` 与 `tools/validation/run_b2_search.py` 执行原 B2 搜索/插入流程；原 `run_contact_candidate_stop.py` 执行停止延续并采集每个物理步。
5. 新入口 `tools/validation/run_native313_stop.py` 负责隔离导入、静态准入和正确归档；`audit_native313_results.py` 专用于审核本轮已保存的旧入口归档错误；`report_native313_validation.py` 从审核数据生成对照和月报图。

## 使用与复现

在 VS Code 打开工作目录 `D:\dsub9项目计划\first_stage_sim\.worktrees\dsub9-v1-contact-validation`。先阅读 [月报图](report_v1/月报_新版完整回归与停止.png)，查看 [机器可读判定](report_v1/assessment.json)。使用既有独立包可以重新运行某一回合：

```powershell
& 'D:\KEYANRUJIAN\python.exe' -X utf8 -B -m tools.validation.run_native313_stop --package-path tmp/mujoco_3_13_probe --tag reproduce_dt0p2_01 --timestep 0.0002
& 'D:\KEYANRUJIAN\python.exe' -X utf8 -B -m tools.validation.run_native313_stop --package-path tmp/mujoco_3_13_probe --tag reproduce_dt0p1_01 --timestep 0.0001
```

必须使用尚不存在的 tag，结果存入本目录的新子文件夹，拒绝覆盖已有记录。新入口的协议键修复有回归测试，并已通过归档检查冒烟验证；本轮没有为它额外运行第三次完整动力学回合。两次正式物理数据来自保留的首次入口。仅使用命令中已记录的 `tmp/mujoco_3_13_probe` 目录：当前入口会检查版本和目录归属，并核验该固定目录的 DLL；尚未支持把任意其他同版本包路径与快照绑定验证。脚本要求本机已存在的隔离包；它不替换系统 MuJoCo，也不会自动安装依赖。

查看证据完整性可运行 `python -m tools.validation.verify_native313_delivery`。图由真实记录绘制，不是预设位姿动画；本项未新增或验收交互式 MuJoCo 播放窗口。

主要记录：[0.2 ms 审核](stop_dt0p2_v1/audited_results.json)、[0.1 ms 审核](stop_dt0p1_v1/audited_results.json)、[静态补充](static_extended.json)、[兼容对照](compatibility_comparison.json)、[执行记录](执行记录.md)、[月报讲解](月报讲解.md)。静态协议与首次结果冻结，新运行不会自动替代它们。

## 下一项完整能力

**在同一独立新版环境重评 B1/B2 七个固定开发工况。** 两种控制器使用相同几何、引擎、物理参数、保护和评价口径，共 14 个配对回合；记录完整成功、受阻、保护和停止结果，并统一制作对比图。不能把旧环境的 B1 与新版 B2 直接当作公平对照，也不应为了证明学习有价值而人为制造传统方法失败。

本项之后仍处于能力 A“基线与训练准入”。七工况重评和共同准入条件满足后，再决定正式迁移以及普通 SAC 训练。旧 SDF DLL 的新版兼容性单独处理。
