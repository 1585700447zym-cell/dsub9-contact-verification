"""Read-only audit of saved MLP/GRU episodes under the 100 nm recovery protocol."""
import math

from tools.learning.noise50_trial import verify_passive_channel
from tools.learning.recovery_learning_contract import (
    LOAD_WARNING_PROTOCOLS, SOURCE_ONLY, digest, protocol_name, validate_config,
)
from tools.learning.recurrent_collection import VERSION
from tools.learning.switchable_sac import load_checkpoint
from tools.learning.time_budget_trial import protocol_config as time_protocol
from tools.validation.consistent_sac_audit import _audit_physical, _read_archive
from tools.validation.recurrent_source_audit import audit_source


def _verify_passive_yaw(raw, *, active_rows):
    """Every completed control cycle has a yaw endpoint, including the stop tail."""
    previous = dict(velocity_rad_s=0., offset_rad=0., updates=0, limited_steps=0)
    for index, frame in enumerate(raw["trace"]):
        if index == 0 and "yaw_admittance" not in frame:
            continue  # Initial native snapshot precedes the first controller command.
        yaw = frame.get("yaw_admittance")
        if (not isinstance(yaw, dict) or yaw.keys() != previous.keys() or
                any(type(yaw[k]) not in (int, float) or not math.isfinite(yaw[k])
                    for k in ("velocity_rad_s", "offset_rad")) or
                any(type(yaw[k]) is not int for k in ("updates", "limited_steps")) or
                not 0 <= yaw["limited_steps"] <= yaw["updates"]):
            raise ValueError("Complete finite passive yaw state required")
        changed = yaw["updates"] - previous["updates"]
        if ((index == 0 and changed != 0) or (changed == 0 and yaw != previous) or
                not 0 <= yaw["limited_steps"] - previous["limited_steps"] <= changed):
            raise ValueError("Passive yaw state changed without its controller update")
        previous = yaw
    proof = verify_passive_channel(raw, True)
    if active_rows and not proof["recurrence_updates_checked"]:
        raise ValueError("Passive yaw ON needs measured feedback updates on an active episode")
    return proof


def audit_recovery_learning_archive(folder, reg, job, *, checkpoint_path, config):
    """Verify persisted evidence against the externally registered source and job.

    The caller supplies an independent registration (physical common fields and
    experiment binding) and job (case, seed, episode_id, exploration_seed,
    deterministic). No simulator, optimizer step or replay publication runs here.
    """
    from tools.model.clearance_task import finish_criteria
    from tools.model.layered_task import GEOMETRY_TOLERANCE_M, TASK_ID
    from tools.learning.newton_damping import NewtonProfile

    config = validate_config(config)
    raw, receipt = _read_archive(folder)
    if (raw.get("version") != VERSION or
            any("execution_contract" in obj for obj in (raw, reg, receipt))):
        raise ValueError("Recovery cycle archive binding required")
    if not isinstance(raw.get("outcome"), dict) or any(
            obj.get(field) is not False for obj in (raw, raw["outcome"])
            for field in ("training_admitted", "valid_for_learning")):
        raise ValueError("Complete quarantined archive and outcome required")
    if (receipt.get("final_reason") == "EXTERNAL_TRUNCATION" or
            any(receipt.get(k, False) is not False for k in ("training_admitted", "valid_for_learning"))):
        raise ValueError("Completed quarantined episode receipt required")
    registered = reg.get("experiment")
    if not isinstance(registered, dict):
        raise ValueError("Independent experiment binding required")
    checkpoint_id = registered.get("source_checkpoint")
    if (not isinstance(checkpoint_id, str) or len(checkpoint_id) != 64 or
            any(c not in "0123456789abcdef" for c in checkpoint_id)):
        raise ValueError("Registered source checkpoint digest required")
    # Restore once from the registered digest. The archive cannot choose the
    # behavior weights, mode, update count, or exploration RNG used to audit it.
    source = load_checkpoint(checkpoint_path, config=config, expected_digest=checkpoint_id)
    binding = source.archive_binding(checkpoint_id)
    if (any(digest(obj.get("experiment")) != digest(binding) for obj in (raw, receipt, reg)) or
            raw.get("policy_mode") != source.policy_mode or
            receipt.get("source_checkpoint_sha256", checkpoint_id) != checkpoint_id):
        raise ValueError("Experiment/checkpoint binding differs")
    if not {"case", "seed", "episode_id", "exploration_seed", "deterministic"}.issubset(job):
        raise ValueError("Complete independently registered episode job required")
    if not isinstance(job["episode_id"], str) or not job["episode_id"].strip():
        raise ValueError("Registered episode identity required")
    for key in ("episode_id", "exploration_seed", "deterministic"):
        if key in receipt and digest(receipt[key]) != digest(job[key]):
            raise ValueError("Receipt and registered job differ: " + key)
    if "source_counts" in receipt and digest(receipt["source_counts"]) != digest(raw.get("source_counts")):
        raise ValueError("Receipt source counters differ")
    speed = config["search_speed_um_s"]
    physical = config["physical_protocol"]
    runtime_pin = physical.get("collision_runtime_sha256")
    if (runtime_pin is not None and
            reg["common"]["runtime"]["compatibility_record_sha256"] != runtime_pin):
        raise ValueError("Mesh contact runtime differs from the registered physical protocol")
    warning_only = protocol_name(config) in LOAD_WARNING_PROTOCOLS
    base_time = {k: v for k, v in time_protocol(speed).items() if k not in SOURCE_ONLY}
    if (digest(raw.get("force_recovery_protocol")) != digest(physical) or
            digest(raw.get("time_budget_protocol")) != digest(base_time) or
            physical["task_referee"] != TASK_ID or config["geometry_tolerance_m"] != GEOMETRY_TOLERANCE_M):
        raise ValueError("Physical protocol or geometry referee binding differs")
    # These are the session's native N2 finish criteria. Receipts cannot waive
    # the depth, force, torque, hold, or final speed requirements.
    profile = NewtonProfile()
    criteria = dict(finish_criteria(), force_N=profile.force_guard_N, torque_Nm=profile.torque_guard_Nm)
    if digest(receipt.get("finish_criteria")) != digest(criteria):
        raise ValueError("Native finish criteria differ")
    replay = audit_source(raw, actor=source.actor, policy_mode=source.policy_mode,
                          checkpoint_id=checkpoint_id, exploration_seed=job["exploration_seed"],
                          deterministic=job["deterministic"], episode_id=job["episode_id"])
    warning_proof = None
    if warning_only:
        from tools.validation.load_warning_audit import verify_load_warnings
        warning_proof = verify_load_warnings(raw, receipt, physical)
    proof = _audit_physical(raw, receipt, reg, job, contract=physical, base_time_contract=base_time,
                            time_budget_group=speed, force_recovery_group=None if warning_only else speed,
                            load_warning_only=warning_only, load_warning_proof=warning_proof)
    if warning_only:
        proof["load_warnings"] = warning_proof
    proof["passive_channel"] = _verify_passive_yaw(raw, active_rows=proof["active_rows"])
    proof.update(verified=True, source_replay_verified=True, action_source=replay,
                 source_checkpoint_sha256=checkpoint_id, optimizer_updates=source.optimizer_updates,
                 config_sha256=binding["config_sha256"], policy_mode=source.policy_mode,
                 physical_protocol_sha256=digest(physical), episode_id=job["episode_id"],
                 valid_for_learning=False, training_admitted=False)
    return raw, receipt, proof
