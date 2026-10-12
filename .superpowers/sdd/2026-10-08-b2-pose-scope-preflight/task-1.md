## Task 1: 纯范围契约与角度贯通

**Files:** 新目录 `scope_contract.py`、`test_scope_preflight.py`。

**Interfaces:** `validate_candidate(candidate: dict, parent: dict) -> dict` 返回校验后的固定候选；`case_kwargs(spec: dict) -> dict` 返回ContactCase具名参数；`script_action(phase: str, elapsed_s: float, enabled: bool, sign: int) -> list[float]`；`next_attempt(entries: list[dict], candidate: dict) -> dict | None`。

- [ ] 写失败反例：P01转换后 `roll_rad == math.radians(0.25)`、`pitch_rad == 0`；J02为−75/+75μm和−0.25/+0.25°；NaN、bool角度、重复ID、错单位、改点或改0.5°守卫全部拒绝。
- [ ] 写脚本边界反例：20ms启用、120ms关闭，STOPPING/回撤/disabled全0，符号只接受±1；固定返回 `[0.1,-0.1,0.1,-0.1]`或反号，不读孔真值。
- [ ] 运行纯测试，确认因缺接口或缺行为失败；实现契约及规范化scope key，不修改父共同配置。
- [ ] 加反例验证固定9/16/25额度、禁止跳点/重复/未知完成后继续；记录普通任务失败可继续、保护或无效必须整批关闭。
- [ ] 在既定worktree运行 `D:\KEYANRUJIAN\python.exe -I -X utf8 -B deliverables/learning_chain/b2_pose_scope_preflight_20261008/test_scope_preflight.py`，预期上述纯测试全部通过，无引擎/网络调用。
