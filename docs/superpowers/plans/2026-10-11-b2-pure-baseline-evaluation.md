# Four-point pure B2 paired evaluation implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Prepare a four-case zero-residual B2 evaluation entry and verify reuse of the eight existing F0/F2000 evaluation archives, without running physics or learning during preparation.

**Architecture:** A standard-library contract checks archive identity, budgets and explicit new authorization. A separate worker uses the same ContinuationResidualSession/controller/referee path as SCOPE20 with constant zero residuals. The parent owns each blocked worker in the existing Windows job helper before releasing GO; all old sources remain unchanged.

**Tech Stack:** Python 3.13 standard library for preparation/tests; the existing pinned CPU/native runtime only for a future authorized physical run.

**Spec:** `deliverables/learning_chain/b2_stratified_evaluation_design_20261011/B2分层工况与普通SAC评价方案.md`

## Global Constraints

- Existing branch/worktree and all uncommitted changes are retained; no commits, cleanup or additional worktree.
- Only J01–J04 from SCOPE20; 25-case extension and C are excluded.
- Future upper bound: four attempts, 14,500 control cycles/145,000 native steps and 1,200 seconds per episode, 7,200 seconds for the package; no retries or old-budget reuse.
- Policy/model/tensor loads, learner constructions, gradient updates and replay publications are zero.
- Same geometry, guard, controller, runtime, functional success and 26-second failure penalty; old 10% result remains failed.
- Preparation and tests use no NumPy, MuJoCo or Torch; missing authorization fails before scientific imports.
- B.2 remains incomplete; RL main-method requirement and B.2-to-C summary reminder remain in force.

## Review Focus

- Frozen archives with matching case names but different actual roll/pitch or task keys must be rejected.
- A stopped ordinary task failure consumes its attempt and permits the next case; invalid/unstopped/protection or runtime faults close the package.
- Interrupted/reordered/duplicate attempts must never be silently resumed or retried.
- Constant zero residual means only the learned correction is zero; baseline axial/angular commands remain active.
- A worker that has not been assigned to its parent's job must not reach physical imports; unauthorized CLI paths cannot create a run.

### Task 1: Archive reuse and bounded contract

**Files:** Create `deliverables/learning_chain/b2_pure_baseline_preparation_20261011/contract.py`, `prepare.py`, `test_preparation.py`.

**Interfaces:** `case_kwargs(point)`, `check_archive(raw, point, role, common_key, expected_score, schema)`, `next_case(entries, cases)`, `require_grant(grant, binding_pin, run_id)`; preparation emits bound configuration, reuse assessment, candidate and source binding.

- [x] Write tests for archive pose/key/update/metric mismatch, failure classification, incomplete attempts and old/incorrect grants.
- [x] Run standard-library unittest under `D:\KEYANRUJIAN\python.exe -I -X utf8 -B`; confirm assertion failures because the implementation is absent.
- [x] Implement the contract and pure-standard-library preparation; bind the eight archive hashes and original SCOPE20 sources.
- [x] Run the tests and the real archive audit; all eight must pass, with historical qualification labels preserved.

### Task 2: Zero-residual entry and supervised worker

**Files:** Create `baseline_entry.py`, `baseline_rollout.py`; extend `test_preparation.py` with zero-action, clock/STOP, import rejection and no-resume cases.

**Interfaces:** `drive_zero(session, clock, stop, cycle_limit, wall_limit, progress)`, `audit_baseline(raw, config)`, CLI `--check`, `--execute`, private `--worker`; only execution after a separately bound new grant can import physics.

- [x] Add failing tests for zero actions in enabled/disabled phases, bounded clock/cycles, source drift and unauthorized CLI rejection.
- [x] Implement the entry using the unchanged factory/controller/referee and existing Windows job ownership/atomic I/O helpers.
- [x] Run the complete standard-library suite; no real worker, model, tensor or physics is constructed.
- [x] Freeze candidate/source hashes; perform one fresh code review, repair material findings with regression tests, and verify once more if changed.
- [x] Publish result/limits, update the five rolling documents and save six snapshots; stop at the completed preparation deliverable.

## Execution rulings

The user approved continuation of the specified preparation. Execute inline, retaining a local `progress.md` ledger in the delivery folder. User instructions override skill defaults to commit, create or delete a separate workspace. Source checks and injected fake-session tests do not qualify a physical outcome; actual four-case data remains pending.
