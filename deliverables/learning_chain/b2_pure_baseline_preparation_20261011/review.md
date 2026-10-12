# 四点纯B2入口独立审查

2026-10-11。审查性质：一次新的只读代码审查，以及同一审查员对原三项问题的定向修复确认。没有运行真实物理、模型、张量、训练或修改文件。审查对象是执行准备，不是四点性能验收。

## 首次审查原文

Critical: none.

Important 1 — baseline_entry.py:94–97: READY requires worker os.getpid() == Popen.pid and only then assigns that PID. The bound executable is the Windows venv redirector (candidate.json, tmp/learning_cpu_20260924/pyvenv.cfg); its native child has a different PID. Existing supervised.py:43–61/process_parent.py explicitly support this launcher chain. Therefore the first real attempt is claimed and then rejected before GO, and failure cleanup only kills the launcher because the job has not yet acquired the native child. Reuse the established registered-parent/launcher validation and own both launcher and verified native worker before GO; cover distinct launcher/worker PIDs with stdlib fakes.

Important 2 — prepare.py:65–81 and baseline_rollout.py:89–95: runtime binding freezes the venv launcher plus the MuJoCo compatibility record, but does not bind/check the base interpreter, pyvenv configuration or installed numerical dependency identity. candidate.runtime.versions/lock_sha256 are recorded but never checked, unlike inherited pilot_worker.prepare_runtime. Changing NumPy in the same venv passes verify_binding and the MuJoCo proof, allowing a purported same-runtime comparison to execute with different numerical code. Add a stdlib pre-import check of the relevant frozen runtime/package identity without importing Torch.

Minor — baseline_entry.py:101–110: a nonzero worker exit jumps over receipt ingestion, so the final package ledger retains only status=claimed even when receipt.json contains accurate error, reset and step counts. Keep the claim, but merge or reference that final receipt on the error path so package cost/failure accounting is immediately complete.

Validation: reran the specified isolated stdlib suite: 23 tests passed; no scientific run. Pose/task mismatch rejection, no-resume order, ordinary-failure continuation and zero-residual baseline composition are sound by inspection. Readiness: repair the Important items before marking this preparation ready for a future grant. Physical results, 25-case expansion, C, training and final paired metric reporting were declined as out of this preparation review’s scope; physical_execution_verified=false remains appropriate. No edits, commits or worktree changes.

## 实施者处理与验证

复用旧supervised.py的bounded_process/enter_gate，不再把Popen启动器PID视为实际解释器PID；原实现分别持有启动器句柄、验证实际子进程关系和分配Job后再发GO。新增不同PID的标准库假进程反例通过。

prepare.py逐项核对旧绑定中的NumPy、NumPy DLL、MuJoCo文件，以及基础解释器/DLL、pyvenv和原锁文件；补充Gymnasium和包元数据绑定。check_runtime在科学导入前核对版本、文件清单、包来源及实际解释器。版本变化和新增数值源码两个反例通过，没有导入Torch。

父进程在finally中收集当前尝试的receipt及监管证据，即使子进程错误退出也保留已计的复位/周期/子步。错误收据反例通过。四个新增反例先RED后GREEN，全套27项通过；最终来源验证单独记录在verification.json和日志。

## 审查员定向确认原文

Targeted confirmation complete: all three original findings are resolved in the inspected source. (1) baseline_entry.py:17–25, 65–67, 101–106 now use the existing bounded_process/enter_gate path, which distinguishes launcher/native identity, owns them before GO, and confirms tree exit. The new regression at test_preparation.py:236 exercises distinct PIDs and ownership-before-GO. (2) prepare.py:54–76, 91–107 pins the inherited numerical inventories and base Python/DLL/venv/lock; contract.py:152–184 checks metadata, inventories and package origins using stdlib, and baseline_rollout.py:89 checks the actual interpreter before selecting/importing physics. This closes the NumPy/runtime drift path I reported. (3) baseline_entry.py:28–37 and 103–106 collect the attempt receipt and supervisor evidence in finally, including failed workers. No additional findings from this targeted confirmation. I did not run physics, edit files or perform a second broad review. Final preparation/rebinding verification remains with your current run; this confirmation does not assert physical success.

行号属于审查当时版本。真实Windows进程树运行和物理评价仍待新登记的实际执行，本审查不升级历史资格或B.2/C验收。
