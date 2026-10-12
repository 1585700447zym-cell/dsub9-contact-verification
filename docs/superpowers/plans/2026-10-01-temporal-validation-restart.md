# Checkpoint-corrected temporal validation restart

> **For agentic workers:** Use superpowers:executing-plans inline. User says continue after writer repair and asks for terminal verification. Preserve worktree changes; no commit, deletion or automatic retry. One fresh read-only reviewer before actual launch.

**Goal:** Finish the already selected 100ms warmup effect validation after correcting the writer failure.
**Architecture:** New immutable execution package copied from the failed package, with the verified binary writer, a real zero-state disk/child-reader gate before any learning, and new durable authority/costs. No lost-state restoration and no modification of old seals.
**Tech Stack:** Existing qualified CPU Python/Torch/SB3/MuJoCo.
**Spec:** deliverables/learning_chain/b2_temporal_learning_restart_20261001/验证方案.md

## Global constraints

New24 dynamics/5000 batches, previous72/cumulative96 dynamics; prior failed500 batches add to temporal family5500 ceiling. C/A2500 each from zero. Original guards/rewards/learning rates/2ms control and four cases unchanged. No old unused credit, no independent test, PAUSED tracking. New fault/guard ends stage without retry.

## Review focus

- Runtime uses the real corrected writer, not only a fixture subclass; zero disk/child-reader gate occurs before formal updates.
- Original failed run and writer repair seals remain byte-for-byte intact; fresh zero does not pretend to recover C500.
- All source/child-reader/parent cost pins are checked before compute; parent cumulative72 and prior500 retained.
- Child-reader failure cannot proceed to training; child performs no neural/optimization/physics calls.
- Terminal operational failure is not a negative policy result; preserved learned checkpoints identify actual triggering policy.

### Task1: new producer and real disk gate

- [ ] Write restart tests for scope72/96/prior500, exact parent seals, real full tensor/archive serialization, and mandatory child gate before training. Watch RED with original producer and missing gate.
- [ ] Copy established stage sources into new package, apply minimal corrected writer and new scope/version/binding; implement full zero checkpoint comparison and independent blocked reader. Expected all new tests GREEN, real calls0.
- [ ] Run related protocol suite plus real checkpoint gate tests; original files untouched.

### Task2: review, seal and actual run

- [ ] One fresh independent review of complete new producer/contract/runner and spec, fix blocking findings with RED→GREEN and suite.
- [ ] Seal exact new sources/runtime/auth, verify byte bindings. Start with corrected zero checkpoint publication and independent read gate.
- [ ] Execute initial4/Ctrain/Cfinal/Crestore/Atrain/Afinal until completion or registered stop. Record new and previous costs separately; no extra diagnostic updates.

### Task3: terminal evidence

- [ ] Re-audit preserved full checkpoints, source bytes, history/RNG/credit, all trajectories and actual costs without computation.
- [ ] Plot evidence, reconcile four rolling documents and same October monthly report; retain immutable snapshots.
- [ ] Independent terminal interpretation check, final seals verified, report actual method outcome and material limitations.
