# SDD ledger — plan: docs/superpowers/plans/2026-10-07-small-boundary-numeric-gate.md

PC-13数值门离线准备

2026-10-07，feature/dsub9-dynamic-actuator-v1，HEAD d2e7e4f，原工作区/全部修改保留。依据已批准PC-11设计与PC-12数值门继续离线实现；不是新研究方向。

Task 1: complete — 缺模块RED后7纯GREEN； 独立数值授权、父/reader共享全局额度与runtime文件绑定。
Task 2: complete — 缺合成协议RED后5纯GREEN；14关联初检通过； 新合成档案和独立进程张量恢复脚本；真实计算不执行。
Task 3: complete — 一次审查原0 Critical/4 Important/1 Minor；作者一轮修复，7反例RED→GREEN，零起点1反例RED→GREEN；总78关联纯检查通过； 候选、一次限定审查、关联纯检查、五份资料与封存。

Ruling: 保留全部未提交修改，故不自动提交/清理/另建工作区；代价是无新Git提交，使用阶段封存快照留证。
Ruling: 当前授权仅覆盖数值门离线准备，关联纯检查可以执行；真正4合成批/32测试状态须明确新计算授权。代价是本轮不能判断数值集成真的通过。

Ruling: 将审查M1由Minor按Important处理 — PC-12数值清单明确要求模型构造/CPU检查点读取另记开销 — 增加透明计数/时长代码；若遗漏会误报4/32的实际计算范围。本轮同一修复pass完成，无二次审查。

验收范围核对：构造器已有同种子四份零更新指纹门；另补空optimizer/replay/历史与三个RNG起点显式断言/零起点证据保存，纯fixture RED→GREEN，实际起点未运行。

Review闭合：I1后置审核失败先留完成收据；I2收据/投影中断只恢复关闭，不重开；I3live launcher树停止与真实PID/创建时间/镜像核验，未知停止保留uncertain/STOP/耗用授权；I4双进程-I与包来源/36文件绑定；M1辅助构造/读取各记尝试/完成/时长。78检查仅纯协议/命令/状态数据；真实torch导入、学习器构造、张量读取、前向、更新、经验发布、物理均0。

保留限制：作者修复无独立二审；Windows真实终止、CPU库加载、Adam/RNG完整恢复未验证。未知完成按确认值至尝试值保留范围，不声称中断时精确完成0。

收口作者自查A1：来源核验失败定位为同名PC12脚本遮蔽；依赖路径装入后新目录置首，实际fresh -I入口反例RED→GREEN。混合pytest另触发1 failed/77 passed，由PC12测试收集重排sys.path造成；反例改为独立-I进程复现真实入口，最终78/78通过，中间失败保留于review_regressions.json。没有二次独立审查。

Stage complete: 数值门脚本、授权请求和离线协议证据交付，真实数值门未授权/未执行。五份资料快照同步，765旧文件/1057共享输入保持，实际计算0、累计208、PAUSED。保留原工作区全部修改，无提交/清理。本阶段完成后暂停汇报并请求具体4/32合成数值授权。
