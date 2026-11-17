"""The warning protocol reaches the same geometry referee and persisted audit entry."""
from copy import deepcopy

import pytest


@pytest.fixture(scope="module", autouse=True)
def qualified_imports_only():
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()


def test_high_contact_force_does_not_veto_geometric_finish_or_hold():
    from tools.model.clearance_task import finish_criteria
    from tools.model.layered_task import functional_finish
    from tools.learning.five_axis_preparation import verify_success_hold

    criteria = dict(finish_criteria(), force_N=5., torque_Nm=.1)
    row = dict(position_m=[0., 0., 0.], quaternion_wxyz=[1., 0., 0., 0.],
               velocity_world=[0.]*6, contact_wrench_G=[0., 0., 12., 0., 0., 0.], penetration_m=0.)
    assert not functional_finish(row, criteria)
    assert functional_finish(row, criteria, force_warning_only=True)
    hold_rows = [deepcopy(row) for _ in range(101)]
    with pytest.raises(ValueError):
        verify_success_hold(hold_rows, task_end_time_s=.2, period=.002, criteria=criteria)
    verify_success_hold(hold_rows, task_end_time_s=.2, period=.002, criteria=criteria,
                        force_warning_only=True)
    for field, value in (("position_m", [.001, 0., 0.]),
                         ("velocity_world", [.1, 0., 0., 0., 0., 0.]),
                         ("contact_wrench_G", [0., 0., 12., .2, 0., 0.])):
        changed = dict(row, **{field: value})
        assert not functional_finish(changed, criteria, force_warning_only=True)


@pytest.mark.parametrize("mode", ["mlp", "gru"])
@pytest.mark.parametrize("protocol", ["load_warning", "load_warning_7pct"])
def test_saved_warning_archive_uses_full_shared_physical_and_source_audit(tmp_path, mode, protocol):
    from tests.test_recovery_learning_audit import stopped_policy_archive
    from tools.learning import load_warning_trial as trial
    from tools.learning.recovery_learning_contract import experiment_config, trial_module
    from tools.learning.recurrent_collection import CyclePolicy
    from tools.learning.switchable_sac import Experiment, save_checkpoint
    from tools.validation.recovery_learning_audit import audit_recovery_learning_archive

    raw, receipt, reg, job, publish, _old = stopped_policy_archive(tmp_path, "gru")
    config = experiment_config(mode, physical_protocol=protocol)
    experiment = Experiment(config)
    path = tmp_path / "warning-source"
    checkpoint = save_checkpoint(experiment, path)
    envelope = experiment.archive_binding(checkpoint)
    for target in (raw, receipt, reg):
        target["experiment"] = deepcopy(envelope)
    receipt["dynamic_config"]["recovery_distance_m"] = .0003
    reg["common"]["dynamic_config"]["recovery_distance_m"] = .0003
    for dynamic in (receipt["dynamic_config"], reg["common"]["dynamic_config"]):
        dynamic.update(actual_speed_limit=.02, actual_angular_speed_limit=.5)
    receipt["controller_config"] = deepcopy(config["physical_protocol"]["controller_config"])
    raw.update(policy_mode=mode, observation_version=trial.OBSERVATION_VERSION,
               force_recovery_protocol=deepcopy(config["physical_protocol"]))
    next(field for field in raw["observation_schema"] if field["name"] == "latched_guards")["source"] = trial.GUARD_SOURCE
    policy = CyclePolicy(mode, experiment.actor, checkpoint_id=checkpoint,
                         exploration_seed=job["exploration_seed"], deterministic=False)
    policy.begin_episode(job["episode_id"])
    for cycle, row in enumerate(raw["transitions"]):
        assert policy.select_cycle(cycle, row["observation"], row["action_active"]) == row["action"]
        row["action_log"]["contract_version"] = trial_module(protocol).VERSION
    raw.update(policy_source=policy.source, source_cycles=policy.records, source_counts=policy.counts)
    policy.end_episode()
    end = raw["trace"][-1]["time_s"]
    position = raw["trace"][0]["position_m"][2]
    samples = [dict(time_s=k*.0002, phase="STOPPING", force_N=0., rotation_rad=0.,
                    position_z_m=position, reference_z_m=position, linear_m_s=0.,
                    angular_rad_s=0., torque_G_Nm=0., penetration_m=0.)
               for k in range(1, round(end/.0002)+1)]
    for peaks in raw["cycle_peaks"]:
        peaks["samples"] = 10
    for frame in raw["trace"]:
        frame["penetration_m"] = 0.
    for facts in (raw["evidence"]["guard_facts"], receipt["guard_facts"]):
        facts["max_rotation_from_start_rad"] = 0.
    warnings = trial.summarize_warnings(samples, task_end_time_s=raw["evidence"]["task_end_time_s"])
    receipt["task_end_time_s"] = raw["evidence"]["task_end_time_s"]
    for target in (receipt, raw["evidence"]):
        target["audit_end_time_s"] = end
    for target in (raw, receipt, raw["evidence"]):
        target.pop("force_recovery", None)
        target["load_warnings"] = deepcopy(warnings)
    publish()
    _, _, proof = audit_recovery_learning_archive(tmp_path, reg, job, checkpoint_path=path, config=config)
    assert proof["verified"] and proof["source_replay_verified"] and proof["load_warnings"]["verified"]
    assert proof["load_warnings"]["native_samples"] == 10000
    assert proof["training_admitted"] is False
    receipt["load_warnings"]["checked_substeps"] -= 1
    publish()
    with pytest.raises(ValueError):
        audit_recovery_learning_archive(tmp_path, reg, job, checkpoint_path=path, config=config)
