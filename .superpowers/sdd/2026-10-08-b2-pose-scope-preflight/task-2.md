## Task 2: 无学习入口与监督

**Files:** 新目录 `run_preflight.py`、`test_scope_preflight.py`；只读复用PC-06 `configuration.json/model.xml`，`tools/learning/v4_session.py`，`tools/validation/run_v4_adapter_preflight.py:make_session` 和既有Windows进程监督实现。

**Interfaces:** `main(argv: list[str] | None = None) -> int`；`--check-only`只检查候选/绑定；`--execute --grant <path> --grant-pin <sha> --output <new_path>`才允许进入runtime。每个原始记录包含 `spec`、`simulation_case`、初始四元数、前后快照、动作、事件、子步峰值、尾段、裁决及实际计数。

- [ ] 写假runtime反例：缺授权、候选pin不符、旧授权/已领取grant、错误来源/模型/runtime、非全新输出路径均在任何引擎构造前拒绝；check-only从空进程运行，检查无MuJoCo/Torch/SB3导入。
- [ ] 实现每次尝试先持久记账、再构造/复位，使用任务1角度参数；每次校验实际初始四元数与案例及原坐标约定相符。一次静态拒绝即停止全部，不能 `allow_initial_contact=True`。
- [ ] 写reset失败、归档角度被写零、子步/回合/总时限超限、STOP到达、进程PID复用/退出不明反例；实现受控停止、原始档案保存和关闭额度。预算检查覆盖停止尾段，进程强停不得冒充有效停稳。
- [ ] 动态零动作/脚本臂均用当前F50会话，按候选顺序执行；禁止模型学习相关构造/读取/推理。每周期保存足够前后上下文，以支持命令/参考/停止审核。
- [ ] 纯测试及来源差分通过后完成一次针对新入口的代码审查；问题修复后运行相关反例。记录没有进行真实初始化/物理实测，形成候选绑定。
