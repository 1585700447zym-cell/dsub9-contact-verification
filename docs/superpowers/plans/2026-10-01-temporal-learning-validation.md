# Temporal learning validation implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline; user explicitly authorizes continuing through verification without intermediate approval. Existing worktree and all changes preserved; no commits/cleanup.

**Goal:** Test whether 100ms warmup repairs the observed learned-policy loss of four-point ability at up to2500 updates.
**Architecture:** Separate pinned validation contract/ledger, requalified new dataset and complete branch checkpoints, supervised physical/update runner, independent restoration worker and offline result audit. Reuse sealed collector safety-tail and physical meter, not its old budget.
**Tech stack:** Qualified Python/CPU Torch/SB3/nativeMuJoCo3.13, existing atomic JSON/whole-episode audit.
**Spec:** deliverables/learning_chain/b2_temporal_learning_validation_20261001/验证方案.md

## Global constraints

24 new dynamics/5000 formal batches, previous68/cumulative92;13000 controls/start; no independent test/old budget/automatic retry/tracking. C first, rates3e-4, frozen guards/2ms policy unchanged. Current authorization must precede runtime/compute. Each attempt charged before actual calls. Preflight raw bytes remain unchanged; learning qualification is new and explicit, fully re-audited.

## Review focus

- Dataset admission false in prior scope must remain false there; current explicit qualification and credit cannot silently promote old candidates.
- Cross-arm full network/Adam/RNG/source identity; equal sample seeds do not promise equal indices for differing dataset sizes.
- Any guard/fault prevents subsequent compute, including fault tails; all original tail results retained.
- Restoration subprocess ancestry, stale ledger, uncertain cleanup and duplicate launch fail closed.
- Finite goal pass vs incomplete comparison/operational fault; no generalization or completeB.2 claim.

### Task 1: exact contract and durable ledger
**Files:** stage validation_contract.py, test_protocol.py, protocol_runner.py.
**Interfaces:** scope(), attempts(), verify_binding(pin), require_authorization(pin,auth), Ledger.start/finish/reserve_update/finish_update/check_live, accounting.
- [ ] Write tests for exact caps/order/authorization, episode/update reservation, credit from4..8audited episodes, guard/fault stop, crossidentity/stale writer, checkpoint gate.
- [ ] Run hardguarded protocol runner: Expected RED missing interfaces, actualcalls0.
- [ ] Implement minimal contract and rerun: Expected GREEN, actualcalls0.

### Task 2: qualified data, complete branch and supervised runner
**Files:** stage learning_runtime.py, run_validation.py, test_protocol.py, seal_execution.py.
**Interfaces:** Dataset.requalify(arm), Branch.update_one/collect/capture/save/restore; physical/learning meters consume task1ledger. Restore worker shares global ledger and pins with dedicated registered parent.
- [ ] Write failing tests for source permission preservation/unique credit, invalid archive reject, zero shared state, dataset-bound checkpoints, control snapshots/safetytail, authorization-before-runtime/duplicate launch, validguard archive without latercompute.
- [ ] Run protocol RED; implement; run new+related collector/RNG/checkpoint/atomic/parent rules protocols, actualcalls0.
- [ ] One fresh independent whole-stage read-only review; fix significant findings withRED→GREEN.
- [ ] Seal sources/pins/runtime/current explicit user authorization; verify before actual execution.

### Task 3: authorized experiment and terminal closeout
**Files:** stage result audit/plots/docs/final verification.
**Interfaces:** run ledger, archives, full checkpoint manifests and process exits; no audit model/physics/optimizer calls.
- [ ] Run initial,Ctraining/final/restored,Atraining/final within exact caps until completion/registered stop.
- [ ] Re-audit all attempts/bytes/credit/RNG/state/cost and stage goal; audit calls0.
- [ ] Update root progress top/B.2/original8/risks/next/log, deliveryoverview,currententry,sameOctober monthly integrated evidence and source log; keep immutable snapshots.
- [ ] Review terminal evidence and seal; report method outcome and limits only at terminal scope.
