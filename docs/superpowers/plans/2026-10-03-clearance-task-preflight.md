# 1.20 mm / 80 μm 共同任务与基线预检实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Preserve all current uncommitted work; no commit, clean or new worktree.

**Goal:** 实现独立版本的新几何/成功判据，完成最多9个纯B2开发回合，判断任务是否有效且有必要继续学习。

**Architecture:** 新任务模块生成256分段主孔、提供80 μm判据与九针配合检查；已有动力学/会话仅增加显式、默认不变的实例参数。独立预检入口保存完整轨迹、保护与停稳事实，不接学习更新。

**Tech Stack:** 已限定Python环境、修复版MuJoCo 3.13、NumPy、pytest、现有B2。

**Spec:** `研究推进计划_当前版.md`中2026-10-03任务调整方案；用户随后明确要求修改计划后直接实施。

## Global Constraints

- 当前工作树及分支保持；不提交、不删除、不修改历史模型/冻结实验/合同。保留现有源码编辑并快照本次触及的原文件。
- 新版本主孔直径1.20 mm、针径1.00 mm、入口1.35 mm；使用实际学习环境的256分段native碰撞，不误用早期128分段默认模型。
- XY成功阈值80 μm，其余深度20 μm、角度0.5°、0.1 s保持、载荷/穿透/停稳标准保持。增加九针保守圆柱配合检查，只用于裁决，控制器不读取孔中心真值。
- 旧模型和默认50 μm行为不变。新模型渲染显示实际碰撞壳体/孔壁，隐藏旧窄孔母头视觉网格；明确是几何核对视图，不伪称已修改旧STEP制造模型。
- 最多9新动态，纯B2、0策略网络、0优化、0独立测试；旧累计109，本轮累计上限118，旧未用余量不结转。自动跟踪保持PAUSED。
- 固定顺序：对准、±X100、±Y100、±X150、±Y150（μm），初始零倾角。初始化或无效仿真、未停稳、运行故障、接触/运动保护均保留证据后停止余点，不重试；普通有效任务失败可继续。
- 本轮只交付新任务的有限开发可用性与难度证据，不授予训练资格，不预设方法效果。阶段完成同步四份滚动资料。

## Review Focus

- 默认调用应保持旧XML和50 μm结果，不出现全局FINISH或模型污染；任务1做并存测试。
- 80 μm但倾角导致某根针超出孔壁时不能成功；任务1做相应反例。
- 新视觉孔径必须与碰撞一致，不能只改母头的非碰撞外观；任务1检查XML语义与静态模型。
- 任一未停稳/保护/初始化失败不得计成功或漏记尝试；任务2做裁决及停止计划测试，实际保存完整物理尾段。
- 现有100 μm工况可能不再有挑战；任务3同时报告预登记150 μm结果，不能只报告有利点或把成功当学习贡献。

## Task 1: 新任务模型和实例化成功条件

**Files:** 新增`tools/model/clearance_task.py`、`tests/task_variants/test_clearance_task.py`；修改`tools/dynamics/cartesian.py`、`contact_candidate.py`、`tools/learning/guarded_environment.py`、`session.py`、`guarded_session.py`、`residual_session.py`及`tools/validation/run_b1_baseline.py`的可选参数。

**Interfaces:** `build_task_xml(file_directory=None)->str`；`pin_fit(row)->bool`；`finish_criteria()->dict`；环境新增`model_xml=None`；会话新增`finish_criteria=None, geometry_checker=None`；`geometric_finish(row, criteria=None)`。

- [x] 保存本次修改前源码、默认XML摘要；写模型/新旧判据/倾斜反例测试并看到失败。
- [x] 实现最小实例参数，所有缺省行为与源文件资产保留；输出新任务XML和元数据。
- [x] 运行新任务测试及受影响会话、动作、停止的离线检查；静态编译核对实际孔壁、针径、无效输入和默认XML未改。

## Task 2: 有限纯B2预检入口

**Files:** 新增`tools/validation/run_clearance_preflight.py`与`tests/task_variants/test_clearance_preflight.py`。

**Interfaces:** 任务1的模型与判据；现有`LearningEnvironment`、`CandidateEpisodeSession`、冻结B2配置及修复运行库。输出`deliverables/task_variants/clearance120_20261003/`中的plan/ledger、XML、逐回合完整档案、summary。

- [x] 先测试固定工况顺序、唯一输出目录、失败计数和保护阻断后续启动，看到失败后实现。
- [x] 一次代码独立审查并处理重要问题，再绑定源码/模型/配置和执行范围。
- [x] 使用前台可轮询进程执行，逐回合预记启动、保存完整轨迹与停止样本，每500周期落盘进度；任何异常不隐式重启。

## Task 3: 实际预检与结果交付

- [x] 静态配合检查与新/旧默认模型核对通过后，执行上述最多9回合，无训练。
- [x] 从落盘数据复核成功、峰值力、接触/SEARCH作用、末端误差、保护和停稳；未执行点明确记未执行。
- [x] 给出进入短训/调整开发分布/停止修模的判断；更新计划、入口、进度、总览、同一10月月报，保存当时文档快照及结果校验清单。

## 执行约定

按用户本轮授权直接实施，不再另设计划审批。使用本任务交付目录的progress.md持续记录；Windows下不运行依赖提交的bash工作区脚本。相关检查覆盖本次变化；全项目测试含未授权长动态/历史运行库，不作为本轮隐式追加物理预算。独立审查在代码完成后、真实动态前进行一次。

## 实际收口（2026-10-03 19:37）

44项相关检查通过；预登记9上限实际8回合，正Y150旋转保护后受控停止、负Y150未执行，符合计划停止规则。8/8有效停稳；本任务实现与有限预检交付完成，不是模型训练资格或B.2验收。下一任务见当前研究计划及新任务诊断。执行时计划原文已随输入保存到source_snapshot，勾选发生在执行结束之后。
