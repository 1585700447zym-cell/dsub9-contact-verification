"""Synthetic admission boundaries and real tensor updates, without physics."""
from copy import deepcopy
import hashlib

import pytest

from tools.learning.recovery_learning_contract import digest, experiment_config
from tools.learning.switchable_sac import Experiment, load_checkpoint, save_checkpoint
from test_recurrent_replay import episode, publish


@pytest.fixture
def admission(monkeypatch, tmp_path):
    from tools.learning import recovery_learning_contract
    from tools.validation import recovery_learning_audit, run_consistent_sac

    qualification = tmp_path / "synthetic-proof.json"
    qualification.write_bytes(b'{"synthetic":true}')
    qualification_sha = hashlib.sha256(qualification.read_bytes()).hexdigest()
    def verify(reg, job, *, config, qualification_path, expected_digest):
        assert digest(reg) == expected_digest and digest(job) in reg["training_jobs"]
        assert hashlib.sha256(qualification_path.read_bytes()).hexdigest() == reg["g1_sha256"]
        assert reg["g1_sha256"] == qualification_sha and job["split"] == "train"
    def audit(folder, reg, job, **kwargs):
        rows = episode(1, [True, False, True, True, False])
        return (dict(transitions=rows, outcome=dict(simulation_valid=True, physical_stopped=True)),
                dict(archive_sha256=hashlib.sha256(job["episode_id"].encode()).hexdigest()),
                dict(verified=True, source_replay_verified=True, synthetic=True))
    monkeypatch.setattr(recovery_learning_contract, "verify_training_registration", verify)
    monkeypatch.setattr(recovery_learning_audit, "audit_recovery_learning_archive", audit)
    monkeypatch.setattr(run_consistent_sac, "select", lambda reg: {})
    return qualification


def request(experiment, checkpoint_digest, episode_id, qualification):
    job = dict(episode_id=episode_id, split="train", deterministic=False)
    reg = dict(stage="G2", experiment=experiment.archive_binding(checkpoint_digest),
               training_jobs=[digest(job)], g1_sha256=hashlib.sha256(qualification.read_bytes()).hexdigest(),
               common=dict(runtime=dict(compatibility_record_sha256="synthetic")))
    return dict(config=experiment.config, reg=reg, job=job)


@pytest.mark.parametrize("mode", ["mlp", "gru"])
def test_admission_persists_provenance_and_bounded_updates(tmp_path, admission, mode):
    from tools.learning.load_warning_pilot_update import admit_episode, optimize

    config = experiment_config(mode, physical_protocol="load_warning")
    exp = Experiment(config)
    path = tmp_path / "fresh"
    pin = save_checkpoint(exp, path)
    for count in range(2):
        req = request(exp, pin, f"synthetic-{count}", admission)
        output = tmp_path / f"admitted-{count}"
        result = admit_episode(tmp_path, req, checkpoint_path=path, output_checkpoint=output,
                               qualification_path=admission, registration_digest=digest(req["reg"]))
        assert result["audit"]["synthetic"] and result["publication"]["committed"] == 5
        assert result["admitted_episodes"] == count+1
        pin, path = result["checkpoint_sha256"], output
        exp = load_checkpoint(path, config=config, expected_digest=pin)
    output = tmp_path / "updated"
    with pytest.raises(ValueError, match="budget"):
        optimize(path, output, config=config, checkpoint_digest=pin, target_updates=3, max_updates=2)
    assert not output.exists()
    result = optimize(path, output, config=config, checkpoint_digest=pin, target_updates=2, max_updates=2)
    assert result["optimizer_updates"] == 2 and result["admitted_transitions"] == 10
    assert len(result["updates"]) == 2
    assert all(0 < row["batch_rows"] <= 256 for row in result["updates"])
    restored = load_checkpoint(output, config=config, expected_digest=result["checkpoint_sha256"])
    state = restored.state_dict()
    assert len(state["training"]["episodes"]) == len(state["training"]["updates"]) == 2
    assert state["training"]["episodes"][0]["registration_sha256"]
    broken = deepcopy(state)
    broken["training"]["episodes"][0]["replay_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="provenance"):
        Experiment.from_state(broken, config)
    assert restored.update_from_replay()["critic_batches"] == 3
    assert len(restored.state_dict()["training"]["updates"]) == 3


def test_unregistered_replay_and_failed_audit_cannot_be_promoted(tmp_path, admission, monkeypatch):
    from tools.validation import recovery_learning_audit

    config = experiment_config("gru", physical_protocol="load_warning")
    exp = Experiment(config)
    path = tmp_path / "fresh"
    pin = save_checkpoint(exp, path)
    req = request(exp, pin, "new", admission)
    def reject(*args, **kwargs):
        raise ValueError("injected audit failure")
    monkeypatch.setattr(recovery_learning_audit, "audit_recovery_learning_archive", reject)
    with pytest.raises(ValueError, match="injected"):
        exp.publish_training_archive(tmp_path, req["reg"], req["job"], checkpoint_path=path,
            qualification_path=admission, expected_registration_digest=digest(req["reg"]), include_audit=True)
    assert len(exp._replay) == 0 and exp.training_summary["admitted_episodes"] == 0
    for i in range(2):
        publish(exp._replay, str(i), episode(1, [True, False]))
    with pytest.raises(RuntimeError, match="not registered|provenance"):
        exp.update_from_replay()
    with pytest.raises(RuntimeError, match="provenance"):
        exp.publish_training_archive(tmp_path, req["reg"], req["job"], checkpoint_path=path,
            qualification_path=admission, expected_registration_digest=digest(req["reg"]))


@pytest.mark.parametrize("mode", ["mlp", "gru"])
def test_nonfinite_update_result_restores_state_and_sampler(tmp_path, admission, monkeypatch, mode):
    from tools.learning.sac_checkpoint import _same

    exp = Experiment(experiment_config(mode, physical_protocol="load_warning"))
    path = tmp_path / "fresh"
    pin = save_checkpoint(exp, path)
    for count in range(2):
        req = request(exp, pin, str(count), admission)
        exp.publish_training_archive(tmp_path, req["reg"], req["job"], checkpoint_path=path,
            qualification_path=admission, expected_registration_digest=digest(req["reg"]))
    before = exp.state_dict()
    updater_state = exp._updater._snapshot()
    rng = exp._mlp.replay_rng if mode == "mlp" else exp._replay_rng
    rng_state = deepcopy(rng.bit_generator.state)
    original = exp._updater.update
    def bad_report(batch):
        return dict(original(batch), critic_loss=float("nan"))
    monkeypatch.setattr(exp._updater, "update", bad_report)
    with pytest.raises(ValueError):
        exp.update_from_replay()
    assert exp.optimizer_updates == 0 and exp.failed_update_attempts == 1
    assert _same(exp._updater._snapshot(), updater_state)
    assert _same(exp._training, before["training"]) and rng.bit_generator.state == rng_state
    with pytest.raises(RuntimeError, match="Healthy"):
        save_checkpoint(exp, tmp_path / "unhealthy")
    assert not (tmp_path / "unhealthy").exists()


def test_optimizer_progress_keeps_completed_costs_on_later_failure(tmp_path, admission, monkeypatch):
    from tools.learning import load_warning_pilot_update as worker

    exp = Experiment(experiment_config("gru", physical_protocol="load_warning"))
    path = tmp_path / "fresh"
    pin = save_checkpoint(exp, path)
    for count in range(2):
        req = request(exp, pin, str(count), admission)
        exp.publish_training_archive(tmp_path, req["reg"], req["job"], checkpoint_path=path,
            qualification_path=admission, expected_registration_digest=digest(req["reg"]))
    path = tmp_path / "admitted"
    pin = save_checkpoint(exp, path)
    original = Experiment.update_from_replay
    def fail_second(self):
        if self.optimizer_updates == 1:
            raise ArithmeticError("synthetic second update failure")
        return original(self)
    monkeypatch.setattr(Experiment, "update_from_replay", fail_second)
    events = []
    with pytest.raises(ArithmeticError, match="second update"):
        worker.optimize(path, tmp_path / "failed", config=exp.config, checkpoint_digest=pin,
                        target_updates=2, max_updates=2, progress=events.append)
    assert [r["status"] for r in events] == ["attempting", "update_completed", "attempting", "failed"]
    assert events[0]["attempted"] == 1 and events[0]["completed"] == 0
    assert events[-1]["attempted"] == 2 and events[-1]["completed"] == 1
    assert events[-1]["optimizer_updates"] == 1 and not events[-1]["checkpoint_saved"]
    assert not (tmp_path / "failed").exists()
    monkeypatch.setattr(Experiment, "update_from_replay", original)
    events.clear()
    result = worker.optimize(path, tmp_path / "success", config=exp.config, checkpoint_digest=pin,
                             target_updates=1, max_updates=2, progress=events.append)
    assert [r["status"] for r in events][-2:] == ["saving_checkpoint", "checkpoint_saved"]
    assert events[-2]["completed"] == 1 and not events[-2]["checkpoint_saved"]
    assert events[-1]["checkpoint_saved"] and events[-1]["checkpoint_sha256"] == result["checkpoint_sha256"]
