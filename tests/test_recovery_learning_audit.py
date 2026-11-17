"""Complete synthetic stopped archives and real saved actor weights; no rollout."""
from copy import deepcopy

import pytest


@pytest.fixture(scope="module", autouse=True)
def runtime_imports_only():
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()


def stopped_policy_archive(folder, mode):
    from tests.test_time_budget_archive import converted_archive
    from tools.learning.force_recovery_trial import protocol_config
    from tools.learning.recurrent_collection import CyclePolicy, VERSION
    from tools.learning.recovery_learning_contract import SOURCE_ONLY, experiment_config
    from tools.learning.switchable_sac import Experiment, save_checkpoint
    from tools.model.clearance_task import finish_criteria

    speed = 450 if mode == "mlp" else 900
    raw, receipt, reg, job, publish = converted_archive(folder, speed)
    template = protocol_config(speed)
    config = experiment_config(mode, search_speed_um_s=speed)
    experiment = Experiment(config)
    checkpoint = folder / "source"
    checkpoint_id = save_checkpoint(experiment, checkpoint)
    for target in (raw, receipt, reg):
        target.pop("execution_contract")
        target["experiment"] = experiment.archive_binding(checkpoint_id)
    job.pop("stage")
    job.update(episode_id="synthetic-stop", exploration_seed=19, deterministic=False)
    raw.update(version=VERSION, policy_mode=mode, episode_id=job["episode_id"],
               observation_version=template["observation_version"], force_recovery_protocol=deepcopy(config["physical_protocol"]),
               time_budget_protocol={k: v for k,v in raw["time_budget_protocol"].items() if k not in SOURCE_ONLY})
    for target in (raw, raw["outcome"]):
        target.update(training_admitted=False, valid_for_learning=False)
    receipt["finish_criteria"] = dict(finish_criteria(), force_N=5., torque_Nm=.1)
    provider = CyclePolicy(mode, experiment.actor, checkpoint_id=checkpoint_id,
                           exploration_seed=job["exploration_seed"])
    provider.begin_episode(job["episode_id"])
    for state in raw["trace"][1:]:
        state["yaw_admittance"] = dict(velocity_rad_s=0., offset_rad=0., updates=0, limited_steps=0)
    for cycle, row in enumerate(raw["transitions"]):
        row["action_log"]["contract_version"] = template["version"]
        assert provider.select_cycle(cycle, row["observation"], row["action_active"]) == row["action"]
    raw.update(policy_source=provider.source, source_cycles=provider.records, source_counts=provider.counts)
    provider.end_episode()
    next(f for f in raw["observation_schema"] if f["name"] == "latched_guards")["source"] = (
        "active_guard_blockers_after_verified_force_recovery")
    for peak in raw["cycle_peaks"]:
        peak["penetration_m"] = 0.
    cumulative = {k: max(p[k] for p in raw["cycle_peaks"]) for k in
                  ("force_N", "torque_G_Nm", "penetration_m")}
    record = dict(events=[], samples=[], fatal_reasons=[], had_force_recovery=False,
                  force_recovery_count=0, completed_force_recovery_count=0, peak_force_N=cumulative["force_N"])
    for target in (raw, receipt, raw["evidence"]):
        target.update(force_recovery=deepcopy(record), cumulative_peaks=deepcopy(cumulative))
    raw["outcome"].update({k: record[k] for k in
        ("had_force_recovery", "force_recovery_count", "completed_force_recovery_count", "peak_force_N")})
    raw["outcome"]["force_recovery_fatal_reasons"] = []
    publish()
    return raw, receipt, reg, job, publish, dict(checkpoint_path=checkpoint, config=config)


@pytest.mark.parametrize("mode", ["mlp", "gru"])
def test_new_checkpoint_sources_share_full_native_audit_without_training_admission(tmp_path, mode):
    from tools.validation.consistent_sac_audit import audit_archive
    from tools.validation.recovery_learning_audit import audit_recovery_learning_archive

    raw, receipt, reg, job, publish, kwargs = stopped_policy_archive(tmp_path, mode)
    def audit():
        return audit_recovery_learning_archive(tmp_path, reg, job, **kwargs)

    loaded, _, proof = audit()
    assert loaded["experiment"] == reg["experiment"] == receipt["experiment"]
    assert proof["verified"] and proof["reference_verified"] and proof["force_recovery"]["verified"]
    assert proof["source_replay_verified"] and proof["action_source"]["audit_cycle_inputs"] == 1000
    assert proof["passive_channel"]["verified"] and proof["passive_channel"]["passive_yaw_enabled"]
    assert proof["passive_channel"]["recurrence_updates_checked"] == 0
    assert proof["action_source"]["audit_encoded_cycles"] == (1000 if mode == "gru" else 0)
    assert proof["stop"]["final_native_samples"] == 10000 and proof["task_outcome"] == "TASK_FAILURE"
    assert proof["optimizer_updates"] == 0 and proof["training_admitted"] is False
    assert proof["audit_physical_initializations"] == proof["audit_optimizer_updates"] == 0
    with pytest.raises(ValueError, match="binding"):
        audit_archive(tmp_path, reg, job)

    reg["experiment"]["source_checkpoint"] = "a" * 64
    with pytest.raises(ValueError):
        audit()
    reg["experiment"] = deepcopy(receipt["experiment"])
    receipt["deterministic"] = True
    publish()
    with pytest.raises(ValueError, match="registered job"):
        audit()
    receipt["deterministic"] = False
    receipt["final_reason"] = "EXTERNAL_TRUNCATION"
    publish()
    with pytest.raises(ValueError, match="Completed"):
        audit()
    receipt["final_reason"] = "UNLOAD_TIMEOUT"
    for target in (raw, receipt, reg):
        target["experiment"]["optimizer_updates"] = 31
    publish()
    with pytest.raises(ValueError, match="binding"):
        audit()
    for target in (raw, receipt, reg):
        target["experiment"]["optimizer_updates"] = 0
    raw["policy_source"]["actor_sha256"] = "a" * 64
    publish()
    with pytest.raises(ValueError, match="actor"):
        audit()
    raw["policy_source"]["actor_sha256"] = loaded["policy_source"]["actor_sha256"]
    receipt["force_recovery"]["force_recovery_count"] = 1
    publish()
    with pytest.raises(ValueError, match="Recovery record"):
        audit()
    receipt["force_recovery"]["force_recovery_count"] = 0
    raw["experiment"]["policy_mode"] = "gru" if mode == "mlp" else "mlp"
    publish()
    with pytest.raises(ValueError, match="binding"):
        audit()
    raw["experiment"]["policy_mode"] = mode
    raw["force_recovery_protocol"]["source_policy"] = "frozen_F4000"
    publish()
    with pytest.raises(ValueError, match="Physical protocol"):
        audit()
    raw["force_recovery_protocol"].pop("source_policy")
    receipt["finish_criteria"]["hold_s"] = 0.
    publish()
    with pytest.raises(ValueError, match="finish criteria"):
        audit()


def test_passive_yaw_requires_complete_endpoints_and_replays_updates():
    from tools.control.yaw_admittance import YawFixedAdmittance
    from tools.validation.recovery_learning_audit import _verify_passive_yaw

    channel = YawFixedAdmittance()
    wrench = [0., 0., 0., 0., 0., .015]
    initial = dict(contact_wrench_M=wrench)
    row = dict(contact_wrench_M=wrench, yaw_admittance=channel.yaw_state())
    raw = dict(trace=[initial, row])
    with pytest.raises(ValueError, match="active"):
        _verify_passive_yaw(raw, active_rows=1)
    channel.command(wrench, .002)
    row["yaw_admittance"] = channel.yaw_state()
    assert _verify_passive_yaw(raw, active_rows=1)["recurrence_updates_checked"] == 1
    row["yaw_admittance"]["velocity_rad_s"] += .001
    with pytest.raises(ValueError, match="recurrence"):
        _verify_passive_yaw(raw, active_rows=1)
    row["yaw_admittance"] = channel.yaw_state()
    row["yaw_admittance"].pop("limited_steps")
    with pytest.raises(ValueError, match="yaw state"):
        _verify_passive_yaw(raw, active_rows=0)
    row.pop("yaw_admittance")
    with pytest.raises(ValueError, match="yaw state"):
        _verify_passive_yaw(raw, active_rows=0)
