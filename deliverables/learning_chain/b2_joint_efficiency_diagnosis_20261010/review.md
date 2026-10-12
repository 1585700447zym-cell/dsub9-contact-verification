# B2-SCOPE-21限定独立审查与修复

当前阶段：B.2第3项；任务：四点耗时与精度离线归因的独立审查，已完成。

审查者：新上下文审查代理 `/root/b2_efficiency_diagnosis_review`，gpt-6-astra。首次审查给出Critical 0／Important 1／Minor 0；聚焦修复复审后剩余均0。审查认可分析、科学报告、路线与5份文档草案，可进入既定发布和封存；发布与封存的实际结果由收口核验另行记录。

## 首次实质核对

- 核对8份gzip档案、12份解释源码、6份发布前快照及当前文档、5份草案和报告／路线／发布器的固定摘要。
- 独立检查42,171周期的阶段时间、奖励与CSV对应，以及8项分析边界测试。确认J01 SEARCH为2.290→5.374秒；J02免去0.782秒UNLOAD和2.814秒SEARCH；成功确认约0.240秒计入任务，约1.760秒审核尾段另列。
- 核对终末载体XY和姿态的附加统计：F0 4/4、F2000 0/4；保留原功能成功各4/4。报告没有将它冒充完整PC-09连续hold加layered几何协议复验。
- 未发现支持“丢动作／搜索审核截断”的证据；目标缺项与唯一学习机制成因明确区分。下一项仅离线共同精度目标／奖励候选，未实现或执行。

## Important 1及关闭证据

发现：发布器只检查草案自身的报告、路线和文档pins，未在复制前确认草案本身的摘要就是审查通过的身份。最终校验虽可发现不一致，但已晚于根文档复制。

修复：[publish_delivery.py第72行](publish_delivery.py)在任何复制操作之前，校验`document_proposal.json`的SHA与`review_resolution.json.document_proposal_sha256`一致；不一致抛出`PermissionError`。

回归测试使用阶段目录内的临时项目，构造“草案内部pins自洽、但与审查身份不符”的反例，同时检查目标字节、快照和更新记录均未改变。修复前[日志](publish_guard_red.log)实际FAIL，修复后[日志](publish_guard_green.log)PASS；[阶段完整标准库测试](stage_tests_green.log)9/9 PASS。反例没有触及真实根文档。发布器修改后刷新草案的publisher pin，首次审查草案保存在[review_first_proposal.json](review_first_proposal.json)。

聚焦复审独立确认上述顺序、反例覆盖和新身份；新草案仅更新publisher pin，5份草案、科学报告和路线未改变，6份根文档仍匹配发布前pins。复审只读，阅读红／绿测试日志，没有重新执行会创建临时文件的测试。

| 身份 | SHA256 |
|---|---|
| 首次审查草案 | b37b18296954070243ca01326ae85a81af5c06a511779b05cb8326b0f0137f5d |
| 修复后实际审查草案 | 7e0f77da806dfdb0c24caf37335b18c3a3dae93c5cbad30948ccd25ee153af1e |
| 修复后发布器 | 5233f34da2f2e978a3d10de1d938b6398d005994297d281a304f8ab7b4d5f1bd |

## 审查边界

未评价策略泛化、critic／熵／数据顺序等学习机制的唯一因果、新奖励有效性、完整PC-09连续hold／layered几何协议复现、范围外历史dirty改动，或尚未发生的实际发布／封存结果。单种子已用开发点不支持独立测试结论，完整B.2/C仍未验收。

[终末行交叉核对](precision_crosscheck.json)明确`pc09_continuous_hold_replayed=false`、`layered_geometry_recomputed=false`，字段为`geometric_finish_at_archive_end`。首次快照的字段名不精确，保留在`precision_crosscheck_first.json`作为更正记录，不能据其字段名声称完整旧协议通过。新增物理、模型、张量、策略／critic前向和更新均0。
