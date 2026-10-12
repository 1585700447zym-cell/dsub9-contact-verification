# 唯一独立审查与一次修复

独立审查：GPT-6-astra/high、fresh-context、只读；0 Critical、5 Important、1 Minor。原审查对象摘要保存在reviewed_source.json。没有二次review；修复后0 Critical/0未解决Important是作者核实状态，不冒称审查员再次通过。

5项Important均经6个明确RED反例失败后修复；学习链整体30项GREEN。逐批尝试/完整结果fsync写journal、失败留history与实际count；学习runtime绑定；资格拒绝旧源码报告；数值预热实际抽样/保持并验证完整恢复；只接受自然完整终末。

审查还在纯内存中复现了预热抽样后旧合成恢复失败，以及“成功奖励+截断”被旧audit接受。修复期间捕获空bytes不能被torch weights_only读取，改为UTF-8文本journal；未放宽安全读取。

审查设置之外的实际动态安全性/成功率/收益交由登记pilot；真实代表复现、最终统计和文档按实测后补。模型对硬件/连续扰动的外推仍未证明。

暂缓Minor：最大116000行检查点的读取规模没有数值测量；300秒是预登记上限。超限即新问题、整轮停，不能追加时间或复跑。当前400行probe只能证明数值完整性。

修复前后摘要、差异和针对性证据见review.json、review_fix_red.txt、review_fix_green.txt；最终受检源码与结果由verification.json绑定。
