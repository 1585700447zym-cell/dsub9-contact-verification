# Inline execution ledger — temporal warmup preflight

Authority: ../b2_temporal_warmup_design_20261001/修复方案.md; user replied “继续” after the concrete 8-dynamic/0-training plan.

Scope: adapt, protocol-check, seal, execute up to 8 paired preflight episodes, audit and report. Stop all remaining episodes on any guard or runtime fault. No training, model inference, old budget carryover or automatic tracking.

Ruling: use the existing requested worktree and preserve every uncommitted change; no new checkout, commits, cleanup or history rewrite.
Ruling: retain the qualified physical collector and atomic writer. A new subclass archives preflight data without publishing learning credit; no optimizer or learned policy is instantiated.
Pre-flight interfaces: the prepared sampler consumes a current cached control snapshot. Collector takes that snapshot before drawing; observations, permission and cycle IDs must agree. Its full PCG64 state and hold state are saved together and verified against the transcript.

Task 1: contract and integration tests — complete: review_fixes_green, 40 passed, actual model/physics/optimizer calls 0. Initial contract/entry RED and publication interface fault retained.
Task 2: entry, preservation seal and independent review — complete: independent reviewer found 3 Important issues; RED counterexamples followed by fixes and fresh read-only re-review, 0 Critical/Important/Minor remain; 103 related protocols passed and execution sealed.
Task 3: authorized bounded physical preflight and evidence closeout — complete: 8 new starts, A4/4+C3/4, all valid/stopped/guard-clear, 49,186 controls, 0 training/model/replay; pre-registered mechanism gate passed. Result review clean; final artifact seal follows.

Task 2 Ruling: physical substep forward is paired local-budget work, not initialization. Real supervisor and disk ownership checks occur before each control cycle, including every fault-tail cycle, and before initialization. Original fault-tail CycleResults are retained separately without fabricated sampling transcript or learning admission.

Task 2: complete — 103 related protocols passed/actual calls 0; clean fresh independent re-review, binding and authorization sealed. One early seal command correctly refused an unfinished test report, no files or execution created.
Task 3: in progress — authorized supervised 8/0 preflight; no budget reuse.

Task 3: complete as bounded execution/closeout — 完成8回合, 8 completed, training/model0; candidate gate passed=True, unused starts=0 not reused. Physical outcome is not a learning repair or B.2 acceptance.

Final review: fresh read-only reviewer and result follow-up, Critical/Important/Minor 0; one stale quick-index Minor fixed. Historical 4149 sealed files, 929 inherited source bytes and 1062 current inputs rechecked unchanged. No new computation or training authority.
