# SDD ledger — plan: docs/superpowers/plans/2026-10-06-v4-learning-pilot.md

200条脏/未跟踪记录，目录与分支核对通过，未发现活跃Python进程。用户已授权准入通过后直接小规模训练。本轮累计起点140，上限168、4000批。PC-03封存239文件，单边界完整成功，不是学习证据。

Pre-flight interfaces: Task1 config/schema+137维ReplayBatch→Task2完整链/检查点→Task3登记runner→Task4封存准入后实际执行→Task5只读审核/文档收口。准入之前只合成网络数值测试及只读旧档案审核，无新动力学。

Ruling: 用户新指令覆盖阶段中途暂停的常规约定；准入准备交付完成后继续已登记pilot，不等待例行批准。
Ruling: 完整原始归档放入自包含检查点，接受磁盘/读取成本以真实核验恢复；预登记300s读取上限，避免旧60s硬超时故障。

Task1: complete — 10项schema/137维SAC与回放检查通过；bool观测禁止先转换float再验证，RED发现后修复。旧冻结模块未改。
Task2: complete — 8项完整检查点/下一动作与更新/损坏拒绝检查通过；新增活动预热门前置于online begin，独立RED→GREEN。合成数值数据与正式物理数据能力分离。
Task3: implemented — 28条交替执行、分支保护停止、共同错误停止、一次性账本、完整checkpoint独立读取、冻结开发评价/独立物理复现。5项runner规则检查通过；待综合离线检查、独立数值恢复及一次整阶段审查，尚未物理准入。
Ruling: 老120维collector不用作137维权限证明，使用新whole-episode链；共享冻结原子写入、停止裁判、SAC算法与边界采样。代价是新链需独立审核。
Ruling: 代表复现子进程只拥有父进程预领取的1条动态额度；子进程进度账本独立，STOP指向主交付目录，避免并发覆盖总账。

Final review: 0 Critical/5 Important/1 Minor；5项确认后一次修复，6反例RED→30 GREEN，未二次审查。Minor读取规模暂缓；所有Declined依实际执行/Task5完成，不预写通过。资格尚未签发、实际动态/正式更新0。

Task4 running: 2026-10-06 17:26，F负Y预热 FULL_SUCCESS/有效/停稳，5885整回合经验入池，完整checkpoint独立读取通过；S负Y进行中。正式更新0，不是学习收益。
Ruling: 辅助快照脚本首调用未select新隔离runtime而拒绝，补显式选择后1057输入复制且全摘要匹配；执行main始终正确select并自行验证。辅助错误未改变执行源或增加动态，记录保留；快照完成时实际源保持资格版。

Task4: 准入/一次性执行已结束，实际结果依assessment；未执行额度关闭。
Task5: 实际档案与完整检查点只读核验、五份文档/滚动月报同步、2827历史文件/1057绑定输入及链接核验完成。B.2未完成，未把缺失/失败当收益。
