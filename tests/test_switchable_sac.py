import json
import hashlib
from copy import deepcopy

import pytest
import torch

from tools.learning.recovery_learning_contract import experiment_config, validate_config


def test_mode_is_the_only_experiment_difference():
    ordinary = experiment_config()
    recurrent = experiment_config(policy_mode="gru")
    assert ordinary["policy_mode"] == "mlp"
    assert ordinary["physical_protocol"] == recurrent["physical_protocol"]
    assert ordinary["learning"] == recurrent["learning"]
    assert recurrent["timing"]["burn_in"] == 256
    assert recurrent["physical_protocol"]["noise_hold_cycles"] == 25
    assert "source_policy" not in recurrent["physical_protocol"]
    assert experiment_config(search_speed_um_s=450)["physical_protocol"]["search_xy_limit_m_s"] == .00045
    recurrent["physical_protocol"]["force_recovery"]["fatal_force_N"] = 7
    with pytest.raises(ValueError):
        validate_config(recurrent)
    with pytest.raises(ValueError):
        experiment_config(policy_mode="gru_reset_each_step")


@pytest.mark.parametrize("mode", ["mlp", "gru"])
def test_load_warning_has_a_separate_900_only_contract_and_checkpoint(tmp_path, mode):
    from tools.learning import load_warning_trial
    from tools.learning.recovery_learning_contract import physical_projection, verify_training_registration
    from tools.learning.switchable_sac import Experiment, load_checkpoint, save_checkpoint

    old = experiment_config(mode)
    assert experiment_config(mode, physical_protocol="recovery") == old
    new = experiment_config(mode, physical_protocol="load_warning")
    assert new["version"] != old["version"]
    assert new["physical_protocol"]["observation_version"] != old["physical_protocol"]["observation_version"]
    assert validate_config(new) == new
    assert new["learning"] == old["learning"]
    with pytest.raises(ValueError):
        experiment_config(mode, search_speed_um_s=450, physical_protocol="load_warning")
    with pytest.raises(ValueError):
        validate_config(dict(new, version=old["version"]))
    native_template = load_warning_trial.protocol_config(900)
    assert physical_projection(native_template, 900, "load_warning") == new["physical_protocol"]
    with pytest.raises(ValueError):
        physical_projection(dict(native_template, task_deadline_s=31), 900, "load_warning")
    for own, other in ((old, new), (new, old)):
        chk = tmp_path / own["version"]
        pin = save_checkpoint(Experiment(own), chk)
        assert load_checkpoint(chk, config=own, expected_digest=pin).config == own
        with pytest.raises(ValueError):
            load_checkpoint(chk, config=other, expected_digest=pin)
    with pytest.raises(ValueError, match="not registered"):
        verify_training_registration({}, {}, config=new, qualification_path=None, expected_digest=None)
    with pytest.raises(RuntimeError, match="not registered"):
        Experiment(new).update_from_replay()


@pytest.mark.parametrize("mode", ["mlp", "gru"])
def test_checkpoint_binds_mode_and_physics(tmp_path, mode):
    from tools.learning.switchable_sac import Experiment, load_checkpoint, save_checkpoint
    config = experiment_config(mode, seed=73)
    experiment = Experiment(config)
    path = tmp_path / "fresh"
    digest = save_checkpoint(experiment, path)
    restored = load_checkpoint(path, config=config, expected_digest=digest)
    for name, value in experiment.actor.state_dict().items():
        torch.testing.assert_close(value, restored.actor.state_dict()[name], rtol=0, atol=0)
    manifest = json.loads((path / "manifest.json").read_bytes())
    assert manifest["policy_mode"] == mode
    for wrong in [experiment_config("gru" if mode=="mlp" else "mlp", seed=73),
                  experiment_config(mode, search_speed_um_s=450, seed=73)]:
        with pytest.raises(ValueError):
            load_checkpoint(path, config=wrong, expected_digest=digest)
    with pytest.raises(FileExistsError):
        save_checkpoint(experiment, path)


@pytest.mark.parametrize("mode", ["mlp", "gru"])
def test_resume_reproduces_next_sequence_action_and_optimizer_step(tmp_path, mode):
    from test_recurrent_replay import episode, publish
    from tools.learning.recurrent_collection import CyclePolicy
    from tools.learning.sac_checkpoint import _same
    from tools.learning.switchable_sac import Experiment, load_checkpoint, save_checkpoint

    config = experiment_config(mode, seed=31)
    original = Experiment(config)
    rows = episode(1, [True, False, True, True, False, True])
    # Synthetic component fixture. No production archive or scientific budget.
    publish(original._replay, "synthetic", rows)
    original._update_from_replay()
    path = tmp_path / "after-update"
    digest = save_checkpoint(original, path)
    restored = load_checkpoint(path, config=config, expected_digest=digest)
    for exp in (original, restored):
        assert exp.optimizer_updates == 1
    policies = [CyclePolicy(mode, exp.actor, checkpoint_id=digest, exploration_seed=17)
                for exp in (original, restored)]
    for policy in policies:
        policy.begin_episode("next")
    for cycle, row in enumerate(rows):
        actions = [p.select_cycle(cycle, row["observation"], row["action_active"]) for p in policies]
        assert actions[0] == actions[1]
    for policy in policies:
        policy.end_episode()
    assert original._update_from_replay() == restored._update_from_replay()
    assert _same(original.state_dict(), restored.state_dict())


@pytest.mark.parametrize("mode", ["mlp", "gru"])
def test_post_sample_failure_restores_sampler_and_requires_healthy_checkpoint(monkeypatch, mode):
    from test_recurrent_replay import episode, publish
    from tools.learning.switchable_sac import Experiment

    experiment = Experiment(experiment_config(mode))
    publish(experiment._replay, "synthetic", episode(1, [True, True, False]))
    sampler = experiment._mlp.replay_rng if mode == "mlp" else experiment._replay_rng
    before = deepcopy(sampler.bit_generator.state)

    def fail_after_sample(batch):
        assert sampler.bit_generator.state != before
        raise ArithmeticError("injected after sampling")

    monkeypatch.setattr(experiment._updater, "update", fail_after_sample)
    with pytest.raises(ArithmeticError, match="injected"):
        experiment._update_from_replay()
    assert sampler.bit_generator.state == before
    assert experiment.failed_update_attempts == 1 and experiment.optimizer_updates == 0
    with pytest.raises(RuntimeError):
        experiment.state_dict()
    with pytest.raises(RuntimeError):
        experiment._update_from_replay()


def test_capture_identity_requires_current_persisted_weights(tmp_path):
    from tools.learning.switchable_sac import Experiment, save_checkpoint

    exp = Experiment(experiment_config("gru"))
    with pytest.raises(ValueError):
        exp.archive_binding("invented")
    sha = save_checkpoint(exp, tmp_path / "saved")
    assert exp.archive_binding(sha)["source_checkpoint"] == sha
    with pytest.raises(ValueError):
        exp.archive_binding("other")
    with torch.no_grad():
        next(exp.actor.parameters()).add_(.001)
    with pytest.raises(ValueError):
        exp.archive_binding(sha)


def test_public_update_requires_two_eligible_episodes():
    from test_recurrent_replay import episode, publish
    from tools.learning.switchable_sac import Experiment

    exp = Experiment(experiment_config("gru"))
    for count in range(2):
        with pytest.raises(RuntimeError, match="two"):
            exp.update_from_replay()
        publish(exp._replay, f"synthetic-{count}", episode(1, [True, False, True]))
    assert exp.update_from_replay()["critic_batches"] == 1


def test_qualified_training_job_only_publishes_audited_archives(tmp_path):
    from test_recovery_learning_audit import stopped_policy_archive
    from tools.learning.recovery_learning_contract import digest
    from tools.learning.switchable_sac import load_checkpoint
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime

    select_qualified_runtime()
    _, _, reg, job, _, source = stopped_policy_archive(tmp_path, "gru")
    exp = load_checkpoint(source["checkpoint_path"], config=source["config"],
                          expected_digest=reg["experiment"]["source_checkpoint"])
    # This independent, synthetic authorization only exercises the post-G1 adapter.
    qualification = tmp_path / "fixture-g1"
    qualification.write_text(json.dumps(dict(verified=True, source_replay_verified=True,
        native_reference_verified=True, physical_protocol_sha256=digest(source["config"]["physical_protocol"]),
        passive_channel=dict(verified=True, passive_yaw_enabled=True, recurrence_updates_checked=1),
        force_recovery=dict(verified=True, completed_force_recovery_count=1))), encoding="utf-8")
    job["split"] = "train"
    reg.update(stage="G2", g1_sha256=hashlib.sha256(qualification.read_bytes()).hexdigest(),
               training_jobs=[digest(job)])
    args = dict(checkpoint_path=source["checkpoint_path"], qualification_path=qualification,
                expected_registration_digest=digest(reg))
    with pytest.raises(ValueError, match="registration"):
        exp.publish_training_archive(tmp_path, dict(reg, stage="G1"), job, **args)
    premature = dict(reg, stage="G3")
    with pytest.raises(ValueError, match="registration"):
        exp.publish_training_archive(tmp_path, premature, job,
                                    **dict(args, expected_registration_digest=digest(premature)))
    with pytest.raises(ValueError, match="job"):
        exp.publish_training_archive(tmp_path, reg, dict(job, episode_id="development"), **args)
    with pytest.raises(ValueError, match="job"):
        exp.publish_training_archive(tmp_path, reg, dict(job, split="test"), **args)
    evaluation = dict(job, deterministic=True)
    wrong = dict(reg, training_jobs=[digest(evaluation)])
    with pytest.raises(ValueError, match="job"):
        exp.publish_training_archive(tmp_path, wrong, evaluation,
                                    **dict(args, expected_registration_digest=digest(wrong)))
    proof_bytes = qualification.read_bytes()
    qualification.write_bytes(b"{}")
    with pytest.raises(ValueError, match="G1"):
        exp.publish_training_archive(tmp_path, reg, job, **args)
    qualification.write_bytes(proof_bytes)
    assert len(exp._replay) == 0
    assert exp.publish_training_archive(tmp_path, reg, job, **args)["committed"] == 1000
    with pytest.raises(RuntimeError, match="already"):
        exp.publish_training_archive(tmp_path, reg, job, **args)

