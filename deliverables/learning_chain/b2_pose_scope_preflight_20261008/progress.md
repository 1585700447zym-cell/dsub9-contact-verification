# SDD ledger — plan: docs/superpowers/plans/2026-10-08-b2-pose-scope-preflight.md

2026-10-08，原worktree；BASE d2e7e4fa4ed0631d9dd1b7b98a121c1e46ea6406。

Ruling: Windows原生执行使用Python提取brief/记录测试，替代依赖bash/sed的skill脚本；保留同一ledger语义。
Ruling: 用户保留全部未提交工作；不提交/删除临时账本，不使用Git范围代替未提交文件审查。
Ruling: 全项目pytest会加载物理/学习运行时；本轮仅准入离线实现，执行新入口完整纯测试及相关既有纯检查，真实引擎/优化测试留待独立授权。
Pre-flight: Task1输出角度/顺序/脚本供Task2；Task2完整档案供Task3，采用前后快照/实际角度/持久尝试。
Ruling: 当前PC-06采用ContinuationResidualSession；按spec保持当前控制来源，替代plan泛称V4ResidualSession。代价：须在新目录构造相同会话，不能调用旧pilot入口。
Task 1: in_progress

Task 1: complete (uncommitted; task1_red.txt 6 expected missing-contract failures → task1_green.txt 6/6 pass).
Task 2: in_progress

Task 2: Ruling: 默认沙箱TEMP写入/清理WinError5，故纯测试夹具保存在worktree/tmp/b2_scope_pure_test_fixtures且不自动删除；不更改生产权限，不请求升级。首轮7个临时目录错误保留日志。

Task 2 implementation: scope_contract + execution_contract + run_preflight + windows_job + physical_worker implemented, final review pending. Task 3 assess/offline_math implemented; synthetic fixtures are not physical evidence. First integrated run combined_initial.txt: 24/24 pass, forbidden engine/ML imports absent.
Ruling: supervision uses Windows Job Object with kill-on-close, owned native-worker assignment after live parent/venv proof and before GO. Microsoft primary API documentation checked; new process tests only inert sleeping Python children, no physics. Existing process_parent validation is reused. Scope expands no physics constants.
Ruling: archived numerical functions are AST-selected from pinned sources to avoid transitive MuJoCo imports; ndarray math only, model/reference/command/reward rules unchanged. Actual compositor inputs are captured at original function call to include STOP/reference-release contexts; no controller modifications.
Ruling: failure penalty remains PC-06 common 26 s (25 s action + 1 s adjudication). Synthetic test initially drafted 25 s was corrected against source before GREEN; no metric change.
Task 2 self-audit: last attempt guard/unfinished erroneously produced CLOSED_COMPLETE; targeted test shows two RED subcases, fixed explicit final eligibility check; final GREEN pending.
Task 3: in_progress. candidate_binding/authorization_request initially generated with 2162 files; must regenerate after source/test changes and before seal. Request is NOT an OPEN grant. No physical execution authorized or run.

Final review: one fresh gpt-6-astra/high read-only review; original disposition not ready, I1-I4 Important, I5 Minor. Full findings and exact author rulings in delivery/review.md.
Final: Ruling: I5 raised to Important — incomplete owned-process cleanup violates process-exit accounting and the outer deadline promise, even though GO prevents unauthorized physics — cost if ignored: untracked lingering process/time.
Final: fixed I1 relocation/claim bypass — registered location regression RED→GREEN.
Final: fixed I2 contradictory guard evidence — six mutation counterexamples RED→GREEN.
Final: fixed I3 absent observation/information gate — missing/vector/raw/schema mutations plus no-information route RED→GREEN.
Final: fixed I4 hard wall supervision — stalled inert audit with GO/confirmed exit, plus closing only this launcher claim RED→GREEN.
Final: fixed I5 assignment failure — owned-handle exit/no-GO regression RED→GREEN.
Final correction suite: review_correction_green.txt 32/32. Integration check found canonical inventory order mismatch (WindowsPath vs string); no missing/extra/changed runtime files. binding_order_red.txt 1 failure → final_tests.txt 33/33, no engine/ML imports. Same author correction pass; no re-review.
Final: Ruling: observation differences remain subject to interpretation — the scope spec did not register a quantitative information threshold, so no new admission threshold is invented — cost: actual paired evidence still needs an explicit route judgment before matched-training registration.
Final: Ruling: physical feasibility and engine-backed worker integration deferred to the new explicit physical grant — inert/pure tests do not establish physics — cost: future preflight may fail and close without retries.
Final: Ruling: stale binding/docs/seal were in-progress housekeeping, not accepted exceptions — regenerated 2167-file binding and CLI check required before seal — cost if omitted: wrong implementation could be claimed ready.
Final: Ruling: original controller/model/historical acceptance remain read-only and scoped — 950 old members/1057 shared inputs/63 raw plus 19 scope-plan members verified — cost: no broader model validity gained.
Final: Ruling: arbitrary hand-written counterfeit grants/internal function execution are outside the supported CLI trust model; grants still need real human evidence — cost: local arbitrary code is not sandboxed by this runner. Normal CLI relocation bypass is fixed.
Final: Ruling: absent recovery remains INSUFFICIENT_COVERAGE — not evidence of recovery success — cost: recovery conditions remain an explicit later gap.
Final: Ruling: finishing-a-development-branch keep-as-is follows existing user authorization — preserve branch/worktree/all dirty files and evidence, do not merge/push/commit/delete or repeat integration questions — cost: user handles later integration.
Task 2: complete (uncommitted; final_tests.txt 33/33 plus existing_parent_tests.txt 12/12, check_only.txt passed, unauthorized request rejected before claim).
Task 3 offline implementation/preparation: complete; source binding final 9c15895cf6c8bac905715275c65dead6a8a48be617a3c197839077c7acf673c6. Physical execution step remains NOT AUTHORIZED, not marked complete. New physics/learning0; cumulative208, automatic PAUSED.
