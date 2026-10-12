# 新零起点重启入口的独立审查

2026-10-01。独立只读审查者 `/root/restart_validation_review`（gpt-6-astra high），无实现代理，未调用物理/模型/Adam；未改任何文件。范围：真实保存生产路径、新身份/成本/父资料绑定、训练前独立reader和故障终点证据。读取初次178全绿后仍发现以下两个实际问题，不能将协议绿直接当作入口可运行。

原结论 Critical0 / Important2 / Minor0，Ready No。Declined to judge 无。

1. 独立reader误用仅支持根supervisor直接/venv子进程的worker guard，实际reader是worker子进程；直接os.getppid比较也错误拒绝合法Windows launcher。实际反例证明额外worker层被旧guard拒绝。修复：reader先用 `require_registered_parent` 校验自身与已声明worker（支持一层launcher），再持有句柄校验worker对应已登记root的实际关系；工作claim与停止栅栏保持。真Windows两级进程反例先失败再通过，错误worker/停止栅栏拒绝，读取流程故障必须阻止initial/update。
2. 离线审核只取finished，实际启动后程序故障的failed attempt可能被漏记并绘成未执行。修复：独立fault_evidence读取每个failed的原档案/状态/错误，实际预算不退款，可用原始来源与策略指纹匹配已保存检查点；完整物理审核失败明确记录，不把不完整故障当完整策略评价。故障保留反例先失败再通过；绘图区分已启动故障与未执行。

作者对两项Important执行一次修复，保留 RED→GREEN 与最终相关套件，未再次派审查。Ready在完整最终相关套件通过后由作者收口；不是审查者重新检查后的新意见。原故障包与离线修复封存已由审查者只读核对一致。

证据：reader_chain_red（其中一项最初夹具路径错误，记录保留）、修正夹具的reader_chain_red2（3项，2失败，0错误）、review_fix_green（3/3）、fault_evidence_red（1失败）、fault_evidence_green（1/1）；均真实模型/优化/物理0。全套结果见 reviewed_restart_green.json/xml。
