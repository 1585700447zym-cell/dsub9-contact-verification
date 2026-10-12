# B2-SCOPE-04 单次只读审查与作者处置

2026-10-08，阶段B.2，任务为审核器离线修复。按requesting-code-review技能派出一名无会话历史的只读审查员，审查新目录实际文件与封存父版差异；未审查空的Git提交差异，未修改或执行物理/学习代码。

## 审查原结论

审查对象的 `repaired_assess.py` SHA256 为 `46a8f34ab233908630dc7a5d807b3b0a5c8ed0705f3b799231401234836f7082`，原文保存为 [reviewed_repaired_assess.py](reviewed_repaired_assess.py)。0 Critical、1 Important、0 Minor；修复该问题前不建议完成验收。

**Important：混合大整数与浮点数会误接受真实差异。** NumPy标量还原后，直接执行整数减浮点仍会丢失整数低位。例如 `np.uint64(2**63+1)` 与 `float(2**63)`，两个方向都错误通过，真实差为1，大于1e-12。原大整数测试只覆盖整数/整数。

审查员还确认旧审核逻辑未被删减，check-only通过，布尔混用和NaN拒绝，未导入仿真/学习库。没有发现封存P01原始数据实际包含上述大整数错误。

## 作者处置

先核实再修改：新增混合大整数/浮点双向反例，实测4个子案例均未抛出应有错误，见 [review_red.txt](review_red.txt)。仅在整数与浮点混合时，用标准库Fraction计算二者已表示数值的确切差，再与原容差比较；整数/整数、浮点/浮点沿用原比较。布尔不当作数值处理。

最终检查见 [final_tests.txt](final_tests.txt)、[inherited_final.txt](inherited_final.txt) 与 [正式修订入口复核](archive_reassessment_final.json)。这是作者按审查意见修复后的回归，无第二轮独立审查。

初轮GREEN的源位置拒绝也留档：[green_tests.txt](green_tests.txt)。测试最初把新模块加载为旧私有名称assess，触发原运行器来源保护；改为独立名称repaired_assess，保留原保护，随后真实档案回归通过。正式修复入口未替换旧运行器模块。

## Declined to judge及作者判定

- 完整档案最终回归：审查员未重复作者正在执行的长检查。作者以最终14项新测试、6项旧审核回归及正式入口10份档案结果负责验证。
- 物理运行器迁移、动态范围和训练准入：本项明确只做离线审核器修复，仍待后续新候选；不得把本项通过解释为物理可执行或范围验收。
- 尚在整理的文档和清单：由作者收口核验，不能以准备状态代替最终证据。
- 全部NumPy扩展类型：没有通用支持声明。只支持 `.item()` 返回普通bool/int/float的NumPy布尔、整数、浮点标量；复数、数组或未能还原的扩展精度标量拒绝。当前生产float64路径已用真实数据验证。

Final author disposition: OFFLINE_AUDITOR_REPAIR_VERIFIED。原失败运行和15个关闭动态不变，完整B.2/C未验收。
