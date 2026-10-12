# SDD ledger — plan: docs/superpowers/plans/2026-10-04-v4-residual-adapter.md

起点feature/dsub9-dynamic-actuator-v1，191项脏/未跟踪。PC-01封存222文件，TV-01～09共2112；累计动态130。当前方案最多9新回合，训练0。

Pre-flight: 命令过滤输出为实际可行的限幅速度，session直接交给env.step再次相同限幅；观测先阶段掩码再构造；runner只在静态门/审查后消费一次性预算。旧ResidualSession不能自行保留参考释放，必须显式调用LayeredReferenceSession._command_for_action。

Ruling: 不修改冻结基类，新增适配器；技能提交/清理要求服从用户保留未提交修改的指示。

Task 1: complete — 14项RED→GREEN；旧6个反例过滤成功，随机边界/继承释放/版本化相对观测/B1检查通过。
Task 2: implementation complete — 一次性runner原6项RED→GREEN；第一轮相关套件292通过。
Final review: fresh independent /root/v4_adapter_review，0 Critical/4 Important/0 Minor。
Final: fixed 整轮异常封闭、STOP启动前检查、实际参考端点门、完整冻结输入/runtime复核；6项RED（含内侧裕量）→25项GREEN。没有延期Minor。
Ruling: 实际trace端点门是本次准入必要检查；不宣称reference_lead裁剪下所有物理子步都满足预测盘。遇越界受控停稳并关闭余量，不以普通失败掩盖接口缺口。

Task 3: complete — v4残差接入的有限预检通过。297项相关检查通过；新增9/9动态、完成9回合，81772控制周期/817720子步；累计139，未执行0关闭。网络调用/训练/独立测试0，自动跟踪PAUSED，B.2未完成。
Task 4: complete pending seal — 结果独立核对、五份滚动资料更新；详见assessment.json。

Final verification complete — 297相关检查；4 Important修复，实际结果按assessment；2334历史文件与新档案/源快照/文档链接校验通过。无训练准入或学习收益结论。
