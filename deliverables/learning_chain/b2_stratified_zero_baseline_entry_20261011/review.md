# 独立只读整体审查原始结论

审查者：stratified_entry_final_review（GPT-6-astra，独立上下文）；2026-10-11。结论：With fixes。审查不授予物理执行资格；没有Critical。

审查了核心源码、配置、登记、绑定、授权和测试，追踪复用驱动、停止裁判和Windows Job。分支/HEAD一致，独立21项合同/审核测试通过，科学模块导入0；未执行物理、模型构造、文件修改或创建worktree。

## Important 1：整包强制终止后未回收当前收据

baseline_entry.py原157～165行只读ledger、附package supervisor并关闭。coordinator已经预约、worker已经构造/复位并写receipt后，外层截止杀掉二者，关闭账本可能仍只保留claimed，从而丢失已落盘构造/复位/控制费用和故障信息。建议树退出后逐预约回收收据，未知尾段标未知/下界，保持不重试。

## Important 2：完整档案但退出证明失败时整份审核中断

assess_results.py原114～120行先添加档案结果，再因receipt_healthy=False与保存healthy=True不一致抛错。worker写完档案后退出超时或非零返回，应该保留为故障/不完整证据，不能阻断全部尝试收口，也不能作为普通成功或26秒失败进入均值。

## Important 3：预约数被误计为累计实测动态

assess_results.py原127～128行使用258+len(episodes)。第一预约后launcher在GO前失败、环境/复位均0时，仍会给出259。建议分列预约槽位、构造尝试、复位尝试/完成、周期/子步，累计沿原实际尝试口径；证据不全标未知，不用预约数推定。

## Minor：缺计划中的成功时间分位数

assess_results.py原44～51行只有成功均值/min/max，没有Task4要求的成功分位数。建议固定中位数/分位数算法，或明确延期。

## Declined to judge

- 新21点真实复位、碰撞、停止及零残差动态表现：本轮无物理授权。
- 新嵌套Windows Job的实际系统表现：只追踪源码，未启动实际监督树。
- 非零SAC、F0/F2000新范围、连续域及完整B.2/C资格：不属于此包离线验收。
- 历史准备测试的目录不存在断言：旧四点授权执行后其时间前提失效，不要求改写旧测试或档案。
- 最终滚动文档、封存摘要及新发布脚本：派单时仍在收口，未纳入核心实现结论。

Assessment：三项Important涉及异常后的证据和计数，建议纯标准库替身RED→GREEN修复后完成离线交付，无需新增科学回合或第二轮审查。作者处理和验证另见review_resolution.json，不将本报告改写为二次独立Clean。
