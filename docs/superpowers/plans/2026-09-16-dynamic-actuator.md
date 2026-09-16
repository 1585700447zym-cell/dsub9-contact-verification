# Dynamic actuator implementation plan

> **For agentic workers:** Use superpowers:subagent-driven-development for independent safety implementation and review; the coupled environment/experiment is integrated locally. Checkboxes track outcomes.

**Goal:** Deliver and measure a bounded dynamic Cartesian simulation, including contact and resolution/time-step checks.

**Architecture:** Preserve all historical artifacts. New dynamic module uses the convex development generator and MuJoCo force integration, with a pure independently tested command/wrench utility. New validation/reporting tools export versioned results and Chinese figures.

**Tech Stack:** Python3.13, MuJoCo3.9.0, numpy, pytest, matplotlib.

**Spec:** docs/superpowers/specs/2026-09-16-dynamic-actuator-design.md

## Global constraints

- Original model/assets/plugins/coverage report unchanged; use existing isolated worktree, new feature branch from86a3733.
- Physical dt0.0001/0.0002/0.0004s, control dt0.002s; parameters explicitly simulation-only.
- No merge, push, real device communication, or training this round.

## Task1: Command bounds and wrench reference points

Files: tools/dynamics/safety.py; tests/dynamics/test_safety.py. Agent owns only these.
Interfaces: limit_command(requested, previous, dt, velocity_limits, acceleration_limits)->np.ndarray; shift_wrench(wrench, source_world, target_world)->np.ndarray. All vectors finite, exact shape6/3, positive limits; invalid input raisesValueError. Component-wise slew then speed clipping; wrench torque = source torque+(source-target)crossforce.

- [ ] Write failures for oversized commands, bounded slew, NaN, and independent moment fixture: F=(1,0,0), source=(0,0,0), target=(0,0,-.0145) gives tau_y=.0145.
- [ ] Implement and run real utility tests.
- [ ] Review utility contract before environment integration.

## Task2: Dynamic environment

Files: tools/dynamics/cartesian.py; tests/dynamics/test_cartesian.py. Consume safety utilities and build_xml. Produce config/environment API in spec.

- [ ] Write failing behavioral tests: finite free motion under command; mass/finite effort causes gradual response rather than teleportation; bounded force; stopping; rejecting overlapped reset; nonfinite command terminates; corresponding contact wrench equals direct contact summation; state only advances by physical time; recover refused while moving and allowed after stopped.
- [ ] Implement PD effort with quaternion error, mj_applyFT atG, real mj_step; per-substep observation/guard, physical stopping, recovery, logs.
- [ ] Run tests, diagnose discrepancies before numerical experiments.

## Task3: Evidence matrix and report

Files: tools/validation/validate_dynamic_actuator.py; tools/reporting/report_dynamic_actuator.py; deliverables/dynamic_actuator_v1/*.

- [ ] Run canonical128/.0002 baseline, no-contact counterfactual, resolution256/.0002 and time steps128/.0001/.0004. Include half and .75 joint errors and original pressure case.
- [ ] Record configuration, actual elapsed times, initial conditions, source hashes, physical-step peaks, termination, traces; keep all failures.
- [ ] Evaluate fixed spec gates, summarize throughput without promising training speed.
- [ ] Render and inspect Chinese plots, write limitations and next-step decision.
- [ ] Independent final code/spec review; verify historical/manifest hashes and regressions; commit locally.

## Execution ledger

Ruling: existing discussion and user approval authorize this dynamic design; proceed without repeated approval. Full robot and real grasp calibration remain deferred per v1.2. Historical files are immutable inputs.

Ruling: native CCD produced a reproducible539.847μm penetration at an almost tangent step-mouth pose, unchanged by iteration counts35/100/200. Preserve the failed baseline, switch only the dynamic configuration to MPR, add the frozen-pose regression and independent geometry/coverage audit, and rerun all dynamic comparisons. No safety threshold is relaxed. This changes the collision backend, not the polygon geometry; static historical coverage remains historical.

Ruling: recovery250μm is a reference budget, not a strict physical displacement cap. Log actual overshoot and add1s recovery timeout. Store first/final stop snapshots separately; use last control sample before0.2s deadline for conservative stop evidence.
