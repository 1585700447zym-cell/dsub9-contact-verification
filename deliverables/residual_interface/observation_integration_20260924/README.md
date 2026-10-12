# B.1阶段内交付：白名单观测、Gym与非零残差联调

日期2026-09-24。**接口联调成果，不是B.1整体验收，更不是SAC训练成果。** 姿态2.5°仍为候选，`training_admitted=false`、`valid_for_learning=false`；没有新增机器人/夹爪，没有使用独立测试集，没有自动提交代码。

## 获得的能力

- 120维固定白名单观测：力历史、相对运动、基线命令、已知控制器/停止/恢复状态和内部参考误差；真值与策略输入分离，原始日志与归一化值分离。
- 四维非零残差接入现有会话，保留世界XY/roll/pitch映射、阶段权限、共同命令限制和变化率限制；零残差仍可作严格对照。
- Gym风格reset/step、完整回合暂存与候选隔离；无效命令、原生引擎异常和非法初始化均留档，不自动重采样。
- 真实外部截断保存截止时next_observation，独立停止尾段不入经验、不替换bootstrap、不补造任务终末奖励。
- 数值损失参照覆盖无权限actor/温度样本排除、critic下一状态无虚构熵收益、任务终止与截断差别。此项不是PyTorch自动微分或SAC适配验收。

字段、来源、单位、尺度、有效位、缓存与调用限制见[观测与调用约定](观测与调用约定.md)。

## 验证状态

| 检查 | 本轮结果与证据 |
|---|---|
| 最终学习接口全目录 | **143/143通过**，0失败/错误/跳过，[tests_final.xml](tests_final.xml)，468.34s |
| 修正后新增接口专项 | 49/49通过，[review_fix_tests.xml](review_fix_tests.xml)，150.57s |
| 七开发工况双重精确回归 | **7/7通过**：36708任务周期+4640尾段周期、413480物理子步；原3/7成功与其余正常失败不变。[机器结果](../residual_observation_regression_20260924/assessment.json)，613.34s |
| 非零动作与恢复 | 20周期非零四轴请求产生同向实际运动；工程化真实回撤过程中屏蔽、恢复搜索后放行，见全目录测试及[test_snapshot](test_snapshot/) |
| 旧非编译套件 | 429通过、1跳过，[legacy_no_rebuild_tests.xml](legacy_no_rebuild_tests.xml)，148.27s；该跳过项另在正确3.13隔离进程中1/1补验通过，[补验记录](legacy_isolated_recheck.xml) |
| 旧SDF编译 | 23项未重跑，冻结DLL哈希保持；未将旧编译结果算成本轮通过 |
| 历史证据保护 | 112交付文件、14原始归档及实际停止裁决重新检查通过 |
| 学习依赖 | PyTorch实际import失败，[依赖记录](依赖记录.json)保留完整错误；元数据中的版本号不作为可用证明 |

之前的13项接续检查、8项Gym首轮及审查反例均保留记录，不覆盖失败事实。各项验证与动态回归并行，耗时不是单进程吞吐或训练预算。

动态入口将零残差送入新观测/奖励/动作层，逐字段与冻结原始归档和上一交付的同守卫版本归档比较；不是只比较最终深度。全部7回合数值有效、实际停止合格，每回合只有一个非零终末奖励。输入809项在运行前后未变，源快照809/809核对一致；另保存21个学习测试快照。归档/源码/报告绑定见[本轮清单](manifest.json)。

独立只读审查发现的异常关闭、失败尝试分母、非有限源计时、实时参考和单字段形状问题，按反例逐项修正，见[审查与修正](独立审查与修正.md)、[执行记录](执行记录.md)。原始动力学、冻结控制器、阈值、奖励目标及旧交付清单均未修改。

## 明确未完成/阻塞

1. PyTorch虽有2.12.1元数据，但实际导入报WinError126；CPU版本目录存在未登记CUDA库的现象，见[学习库阻塞记录](学习库阻塞记录.md)。没有修复或替换用户全局环境。
2. 因此尚未验证张量梯度、优化器跳步、实际SAC适配、未训练模型保存加载与学习计算成本。不能将NumPy参照替代这些准入门。
3. 姿态范围/新增接触探索的代表动态证据与参数冻结、完整初始化范围与吞吐预算仍待完成；2.5°不是刚性硬上限。
4. 当前所有候选经验一律隔离；Gym风格接口不可直接交给通用自动复位/TimeLimit/SB3学习入口。后续收集器必须遵守回合审核协议。
5. 全量旧SDF编译测试本轮23项未重跑，以免覆盖冻结DLL；此前编译结果只作历史记录，不追认为本轮通过。

## 复现

固定工作目录 `D:\dsub9项目计划\first_stage_sim\.worktrees\dsub9-v1-contact-validation`，原分支及未提交修改保留。两个MuJoCo版本测试必须用独立进程，不能混用导入。

```powershell
& 'D:\KEYANRUJIAN\python.exe' -X utf8 -B -m pytest -p no:cacheprovider -q tests/learning
& 'D:\KEYANRUJIAN\python.exe' -X utf8 -B -m tools.validation.verify_residual_observation --tag <全新目录名> --workers 4
& 'D:\KEYANRUJIAN\python.exe' -X utf8 -B -m pytest -p no:cacheprovider -q tests --ignore=tests/learning --ignore=tests/sdf/test_plugin_build.py
& 'D:\KEYANRUJIAN\python.exe' -X utf8 -B -m tools.validation.verify_native313_matrix_delivery
```

动态比较期间不得改源码/模型/资产/配置；运行入口保留输入指纹及源快照，拒绝覆盖已有tag。测试耗时与并行回归耗时不是单环境训练吞吐或SAC学习预算。

## 下一项

先解决隔离学习依赖与真实张量/SAC适配的可运行性，再补B.1范围、姿态冻结、成本及序列化准入。所有门齐全前不进入B.2短训。已同步更新[当前进度](../../../项目进度跟踪.md)和[本轮月报](月报素材.md)。
