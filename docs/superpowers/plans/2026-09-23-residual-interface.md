# 阶段 B.1 残差接口与训练准入实施计划

> **For agentic workers:** 使用 superpowers:executing-plans 顺序实施本计划；若用户明确选择并行代理，再使用 superpowers:subagent-driven-development。以下复选框均是尚未执行的代码工作，不因文档交付而勾选。

**Goal:** 交付共用回合管理与四维残差接口，并用实际证据判断首次短训是否准入。

**Architecture:** 复用冻结动力学和B2，在独立学习目录中建立实例级采样、会话状态、残差映射和回合经验审核。基线/训练/评价共享同一状态机，历史运行器作为逐周期参照。

**Tech Stack:** 当前Windows工作树、`D:\KEYANRUJIAN\python.exe`、隔离MuJoCo 3.13.0、NumPy、pytest；Gymnasium/PyTorch/SAC库在兼容性实测后显式冻结，禁止覆盖历史MuJoCo安装。

**Spec:** [共用回合管理设计](../specs/2026-09-23-residual-session-design.md)及[训练合同v3](../../stage_b/训练合同_v3.md)。

## Global Constraints

- 固定工作目录 `D:\dsub9项目计划\first_stage_sim\.worktrees\dsub9-v1-contact-validation`；保留现有未提交修改；不建立主分支干净副本。
- 物理步0.2ms、控制步2ms、native、256段、ccd_tolerance=1e-12；核对隔离包与DLL。
- 四维残差幅度分别为0.00015m/s、0.00015m/s、0.005rad/s、0.005rad/s；总命令及原恢复预算按v3。
- v3首版策略周期2ms、折扣时间常数10s。降频候选独立登记与验证，不能隐式替代。
- 姿态守卫限值没有已验证默认值；必须取得参数冻结记录后才准入，不能用观测归一化尺度代替。
- 历史实验、源快照、合同v2和旧manifest保留。新实现不直接更新其哈希来掩盖差异。
- B.1不运行独立测试、不进行SAC学习更新。策略保存加载可用未训练模型测试，不能交付为已训练权重。
- 每个步骤的代码和测试需要实际执行；阶段B.1全部要求满足后才汇报为已验收，更新进度与月报后暂停。

## Review Focus

- 同一控制周期重复observe/prepare/render，不得重复更新基线；由任务2测试。
- 输入非有限动作及STOPPING尾段首次超限，必须保留原始原因且不重启时钟；由任务3/4测试。
- 有限物理越界与数值无效、同时发生多种故障必须分别保存并正确裁决；由任务1/3测试。
- 复位、两个环境交错推进、回撤后再停，不能混用历史/峰值/停止时间；由任务2/3测试。
- 全回合丢弃及外部截断后收尾，不能污染经验池或把reset观测作为bootstrap；由任务4测试。

## 任务1 环境指纹与结果协议

**Files:** 新建 `tools/learning/__init__.py`、`runtime.py`、`types.py`、`outcome.py`；测试 `tests/learning/conftest.py`、`test_runtime.py`、`test_outcome.py`。相对路径均位于本工作目录。

**Interfaces:** `verify_runtime(package_path: Path) -> dict`先校验固定兼容记录中的模块路径、版本和DLL；不允许导入了另一版MuJoCo后再切包。`classify_outcome(*, simulation_valid: bool, contact_guard: bool, motion_violation: bool, full_success: bool, physical_stopped: bool) -> dict`至少返回数值有效性、任务类别和学习有效性；初始实现不以“是否有限”作为数值有效性的全部依据。

- [ ] 记录现有依赖版本和可用学习库，不安装或替换历史环境；如需依赖，先确定隔离安装与复现方式。
- [ ] 为错误路径/DLL、错误版本、提前导入冲突写失败测试；测试导入顺序先运行runtime检查再导入动力学。
- [ ] 固定协议反例，再实现与协议对应的最小类型和分类器。例如：

```python
def test_finite_motion_failure_is_not_automatically_invalid():
    r = classify_outcome(simulation_valid=True, contact_guard=False,
        motion_violation=True, full_success=False, physical_stopped=True)
    assert r['simulation_valid'] is True
    assert r['task_outcome'] == 'MOTION_VIOLATION'
    assert r['valid_for_learning'] is True

def test_contact_guard_beats_success_and_motion_violation():
    r = classify_outcome(simulation_valid=True, contact_guard=True,
        motion_violation=True, full_success=True, physical_stopped=True)
    assert r['task_outcome'] == 'CONTACT_GUARD'
```

- [ ] 运行对应测试，确认先因缺失实现/错误行为失败，再通过。另覆盖simulation_valid=False和physical_stopped=False不可学习。

## 任务2 无残差共用会话与周期缓存

**Files:** 新建 `tools/learning/session.py`；补充`types.py`；测试 `tests/learning/test_session.py`、`test_zero_residual.py`。读取原 `run_b2_search.py`、`search_recovery.py`和冻结七工况轨迹作参照，不先修改它们。

**Interfaces:** 实现设计中的`EpisodeSession.reset(case, seed)`、`prepare_cycle()`、`advance_cycle(action4)`、`observe()`。`CycleSnapshot`提供`cycle_id`、`time_s`、`base_command`、`residual_enabled`和状态副本。最初只接受零残差，先证明时序和回合行为。

- [ ] 将原恢复/终止局部变量逐一映射为会话字段，列明reset值和唯一修改位置；控制器重建保证历史清空。
- [ ] 用计数控制器测试同周期缓存，以及首周期/下一周期交界，测试示例：

```python
def test_prepare_is_read_only_after_first_prepare(session):
    before = session.prepare_cycle()
    state = session.controller_state_snapshot()
    for _ in range(3):
        assert session.prepare_cycle().cycle_id == before.cycle_id
        session.observe()
    assert session.controller_state_snapshot() == state
```

`controller_state_snapshot()`为只读诊断接口，返回纯Python标量/列表的独立快照，包含历史、导纳和相位；不得作为policy观测整包暴露。

- [ ] 按原逐周期前置/后置顺序实现会话；失败决定时间、真实STOPPING起点和成功保持分别保存。
- [ ] 测试两次reset、两实例交错执行、搜索切换及等待恢复；禁止全局替换MuJoCo函数。
- [ ] 在精确冻结环境下比较七个历史B2回合：原始命令、受限命令、位置/姿态/速度、阶段、事件、终止和原任务窗口。安全延续按原归档单独对齐，不用尾段追认成功。预先记录容差与差异处理，先定位差异而非修改门槛。

## 任务3 子步统计与共同守卫

**Files:** 新建 `tools/learning/environment.py`；补充`outcome.py`、`session.py`；测试 `tests/learning/test_cycle_statistics.py`、`test_guard_events.py`、`test_recovery.py`。

**Interfaces:** `LearningEnvironment`基于独立native实例扩展周期统计，暴露`begin_cycle()`与`cycle_peaks`；每次物理子步记录F/T及相关事件。`EpisodeSession`消费完整事实集合，再调用分类器；不混用旧矩阵的无效分类。

- [ ] 写周期统计反例，例如先出现0.020N、下周期0.005N时，后周期峰值必须为0.005N而累计值保持0.020N。用测试采样器输入指定子步，避免依赖碰撞求解误差验证统计逻辑。
- [ ] 实现实例级采样钩子，保持原积分/forward/驱动顺序；测试初始采样与周期统计不串扰。
- [ ] 测试STOPPING中首次0.026N事件被锁存、停止起点不变；同时超限按v3优先级而非代码if先后决定。
- [ ] 对姿态范围形成明确参数记录：定义相对初始角度、检查坐标、几何可信边界、旧基线实际姿态包络及候选边界的动态处置。无配置或无证据时入口拒绝准入，禁止给无限默认值。
- [ ] 以合成有限姿态测试边界内/外守卫；再在代表动态回合验证停止，不能把合成测试当动态验收。
- [ ] 恢复覆盖正常回撤/恢复、实际回撤不足、等待超时、历史保护禁止恢复；确认参考位移事件不等于实际回撤完成。
- [ ] 新共同守卫实际改变历史行为时，登记新版本和受影响对照重评范围；通过同版本B2与零残差比较后才继续，不将其伪装成原版本完全一致。

## 任务4 残差观测奖励与经验隔离

**Files:** 新建 `tools/learning/action.py`、`observation.py`、`reward.py`、`episode_buffer.py`、`env.py`；测试 `tests/learning/test_action.py`、`test_observation.py`、`test_reward.py`、`test_episode_buffer.py`、`test_truncation.py`。

**Interfaces:** `map_residual(action4, *, enabled: bool) -> np.ndarray`返回六维速度残差；总命令再做阶段/环境限制。`EpisodeBuffer.stage(transition)`暂存，`finalize(*, valid_for_learning: bool, sink)`一次性提交或隔离，重复finalize拒绝或幂等但不能重复写入。Gym风格env委托session。

- [ ] 写尺度/坐标、所有阶段掩码、NaN/Inf与错误维度测试；即使阶段屏蔽，也必须把无效输入留为无效命令。例如：

```python
def test_four_axes_and_disabled_action():
    a = np.array([1., -1., 1., -1.])
    np.testing.assert_allclose(map_residual(a, enabled=True),
        [.00015, -.00015, 0., .005, -.005, 0.], rtol=0, atol=1e-15)
    np.testing.assert_array_equal(map_residual(a, enabled=False), np.zeros(6))
```

- [ ] 按白名单构建观测、固定尺度及有效位；用不同privileged字段注入测试确保不直接进入策略向量，物理反馈的真实变化不应被错误屏蔽。
- [ ] 写最大推进、每周期载荷、静止/往返、成功与保护冲突、唯一终末奖励和不同Δt累计的数值反例，再实现奖励模块。
- [ ] 测试暂存未完成不能被sink读取，后期数值异常导致整段不提交，有效保护失败可提交，重复finalize不重放样本。例如：

```python
def test_late_invalidity_discards_whole_episode(buffer, sink, transition):
    buffer.stage(transition)
    assert len(sink) == 0
    buffer.finalize(valid_for_learning=False, sink=sink)
    assert len(sink) == 0
```

- [ ] 测试任务预算terminated、批次边界不中止、外部截断truncated互斥；保存截断真实next_observation，安全收尾不覆盖它。
- [ ] 明确四维经验动作与六维执行日志的区别、actor/温度权限掩码及critic下一状态熵项；以确定性测试网络验证停止样本不会引入动作熵收益。
- [ ] 运行对应纯逻辑检查和零残差回归，确认加入观测/奖励/日志不改变物理和基线。

## 任务5 范围预检成本与准入交付

**Files:** 新建 `tools/validation/verify_residual_interface.py`、`tests/learning/test_admission.py`；输出写入全新tag下的 `deliverables/residual_interface/`，不覆盖旧尝试。

**Interfaces:** 验收入口接收明确配置、隔离包路径、新tag和种子；检查缺失/失败时结果写`training_admitted=false`，全部必需证据满足才写true。准入结果同时列明允许的分布、姿态范围、策略周期及代码/环境指纹。

- [ ] 聚合前四项测试结果，拒绝把“有合同文件”当通过；检查输入指纹和实际生效参数。
- [ ] 工程XY域检查中心、四角和预登记固定种子随机点；分别记录初始化与代表动态结果。残差非零会产生新接触/倾角，另执行有界动作响应检查。
- [ ] 用开发案例登记有接触学习的前置检查，确认反馈及残差有效作用；旧±100μm结果只能作选择依据，不能代替新接口的动态预检。不运行独立测试。
- [ ] 测量无界面模型初始化、控制采样、日志/审核成本和学习库无经验更新的计算成本；给出首训预算估算和设备分工依据，注明不是实际学习耗时。
- [ ] 测试未训练策略/确定性策略保存加载后观测、动作和固定评价一致，标为序列化检查，不作为学习权重。
- [ ] 生成准入清单、配置、运行命令、源码/环境指纹、限制、检查报告和月报。任一必需门失败时提交真实阻塞，不启动训练。
- [ ] 更新根目录`项目进度跟踪.md`并汇报B.1结果；B.2训练另以该结果进入。

## 验证运行方式

所有测试从本工作目录执行，`tests/learning/conftest.py`必须先验证并选择隔离运行时；没有这一步不能直接导入环境后宣称用的是3.13.0。

```powershell
& 'D:\KEYANRUJIAN\python.exe' -X utf8 -B -m pytest -p no:cacheprovider -q tests/learning
& 'D:\KEYANRUJIAN\python.exe' -X utf8 -B -m tools.validation.verify_native313_matrix_delivery
```

第一条是拟建测试目录完成后的命令，本次文档交付没有执行它；第二条用于确认历史交付不被破坏。不得把整个项目、SDF插件或实物适用性写成全部验证通过。代码提交只在用户明确要求或既有授权允许时进行，不自动提交其他未跟踪成果。
