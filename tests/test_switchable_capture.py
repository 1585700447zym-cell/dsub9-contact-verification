"""Check the persistent entry using real checkpoints and a five-cycle session double."""
import gzip
import hashlib
import json
from dataclasses import asdict, dataclass
from types import SimpleNamespace

import pytest

from tools.learning.recovery_learning_contract import experiment_config
from tools.learning.switchable_sac import Experiment, save_checkpoint
from tools.validation.recurrent_source_audit import audit_source


@dataclass
class Config:
    setting: int = 1


def inputs(tmp_path, monkeypatch, mode, physical_protocol="recovery"):
    from test_recurrent_lifecycle import Session
    from tools.learning import switchable_capture as capture

    session = Session()
    from tools.validation.yaw_pilot import pilot_cases
    point = pilot_cases()[0]
    job = dict(case=asdict(point), seed=4, episode_id="synthetic-46",
               exploration_seed=19, deterministic=False)
    model = b"<synthetic/>"
    common = dict(actual_model={}, effective_kd=[], dynamic_config={}, runtime={},
                  model_xml_sha256=hashlib.sha256(model).hexdigest())
    config = experiment_config(mode, physical_protocol=physical_protocol)
    experiment = Experiment(config)
    checkpoint = tmp_path / "source"
    pin = save_checkpoint(experiment, checkpoint)
    reg = dict(common=common, experiment=experiment.archive_binding(pin))
    session.env.reference_checks = {}
    session.reason = "TEST_COMPLETE"
    session.finish_criteria = {"force_N": 4.1}
    session.controller = SimpleNamespace(config=Config())
    monkeypatch.setattr(capture, "_open_session", lambda *args: (session, point, model, common))
    return capture, config, checkpoint, experiment, reg, job, session


@pytest.mark.parametrize("mode", ["mlp", "gru"])
def test_load_warning_capture_uses_own_schema_and_evidence(tmp_path, monkeypatch, mode):
    from tools.learning import load_warning_trial
    capture, config, checkpoint, source, reg, job, session = inputs(tmp_path, monkeypatch, mode, "load_warning")
    session.contract = load_warning_trial.protocol_config(900)
    session.observations.version = load_warning_trial.OBSERVATION_VERSION
    session.env.warning_samples = [
        dict(time_s=(k+1)*.0002, phase="RUNNING", force_N=6.5 if k == 3 else .1, rotation_rad=0.)
        for k in range(50)]
    session.env.guard_facts = {"checked_substeps": 50}
    session.env.config = SimpleNamespace(timestep=.0002)
    folder = tmp_path / "warning"
    receipt = capture.capture_quarantined(folder, reg, job, config=config, checkpoint_path=checkpoint)
    raw = json.loads(gzip.decompress((folder / "episode.json.gz").read_bytes()))
    assert raw["force_recovery_protocol"] == config["physical_protocol"]
    assert raw["observation_version"] == session.observations.version
    warnings = raw["load_warnings"]
    assert warnings == raw["evidence"]["load_warnings"] == receipt["load_warnings"]
    assert warnings["checked_substeps"] == 50
    assert warnings["metrics"]["FORCE_GT6_N"]["samples"] == 1
    assert not any("force_recovery" in item for item in (raw, raw["evidence"], receipt))
    assert not receipt["training_admitted"] and not raw["valid_for_learning"]
    assert audit_source(raw, actor=source.actor, policy_mode=mode, checkpoint_id=reg["experiment"]["source_checkpoint"],
                        exploration_seed=19, episode_id=job["episode_id"])["verified"]


def test_capture_rejects_wrong_physical_session_before_reset(tmp_path, monkeypatch):
    capture, config, checkpoint, _, reg, job, session = inputs(tmp_path, monkeypatch, "mlp", "load_warning")
    session.reset = lambda *args, **kw: pytest.fail("cross-protocol physical reset")
    with pytest.raises(ValueError, match="registered physical"):
        capture.capture_quarantined(tmp_path / "wrong-session", reg, job, config=config, checkpoint_path=checkpoint)


@pytest.mark.parametrize("name", ["recovery", "load_warning"])
def test_capture_opens_the_selected_environment_and_session_together(monkeypatch, name):
    from tools.learning import newton_profile, switchable_capture
    from tools.learning.recovery_learning_contract import trial_module
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()
    from tools.validation import run_consistent_sac
    from tools.validation.yaw_pilot import pilot_cases
    trial = trial_module(name)
    env = SimpleNamespace(profile=None)
    selected = object()
    def session_factory(speed):
        assert speed == 900
        def construct(environment):
            assert environment is env
            return selected
        return construct

    monkeypatch.setattr(trial, "environment_class", lambda: lambda: env)
    monkeypatch.setattr(trial, "session_class", session_factory)
    monkeypatch.setattr(run_consistent_sac, "select", lambda reg: {})
    monkeypatch.setattr(newton_profile, "build_model_xml", lambda profile: "<model/>")
    monkeypatch.setattr(switchable_capture, "actual_common", lambda *args: {})
    config = experiment_config(physical_protocol=name)
    registered = {"common": {"runtime": {"compatibility_record_sha256": "synthetic"}}}
    native, _, _, _ = switchable_capture._open_session(config, registered, {"case": asdict(pilot_cases()[0])})
    assert native is selected


@pytest.mark.parametrize("mode", ["mlp", "gru"])
def test_restore_capture_persist_and_reopen(tmp_path, monkeypatch, mode):
    capture, config, checkpoint, original, reg, job, session = inputs(tmp_path, monkeypatch, mode)
    folder = tmp_path / "capture"
    receipt = capture.capture_quarantined(folder, reg, job, config=config, checkpoint_path=checkpoint)
    assert receipt == json.loads((folder / "receipt.json").read_bytes())
    data = (folder / "episode.json.gz").read_bytes()
    assert hashlib.sha256(data).hexdigest() == receipt["archive_sha256"]
    assert (folder / "model_used.xml").read_bytes() == b"<synthetic/>"
    raw = json.loads(gzip.decompress(data))
    assert raw["experiment"] == receipt["experiment"] == reg["experiment"]
    assert raw["case"] == job["case"]
    assert receipt["status"] == "finished" and receipt["reset_attempted"] == 1
    assert not receipt["training_admitted"] and not receipt["valid_for_learning"]
    assert receipt["finish_criteria"] == session.finish_criteria
    assert not any(k in raw["force_recovery_protocol"] or k in raw["time_budget_protocol"]
                   for k in ("source_policy", "optimizer_updates", "frozen_policy_compatibility"))
    assert audit_source(raw, actor=original.actor, policy_mode=mode,
                        checkpoint_id=reg["experiment"]["source_checkpoint"],
                        exploration_seed=19, episode_id=job["episode_id"])["verified"]
    with pytest.raises(FileExistsError):
        capture.capture_quarantined(folder, reg, job, config=config, checkpoint_path=checkpoint)


def test_failed_collection_preserves_partial_cost_without_publication(tmp_path, monkeypatch):
    from tools.learning.five_axis_collection import CollectionError
    capture, config, checkpoint, _, reg, job, session = inputs(tmp_path, monkeypatch, "gru")
    def failed_step(action):
        raise RuntimeError("injected step failure")
    session.advance_cycle = failed_step
    folder = tmp_path / "partial"
    with pytest.raises(CollectionError, match="injected step failure"):
        capture.capture_quarantined(folder, reg, job, config=config, checkpoint_path=checkpoint)
    receipt = json.loads((folder / "receipt.json").read_bytes())
    raw = json.loads(gzip.decompress((folder / "episode.json.gz").read_bytes()))
    assert receipt["status"] == "error" and receipt["reset_attempted"] == 1
    assert receipt["source_counts"]["actor_head_calls"] == 1 and receipt["control_cycles"] == 0
    assert not receipt["valid"] and not raw["valid_for_learning"]


def test_stale_binding_rejected_before_session_creation(tmp_path, monkeypatch):
    capture, config, checkpoint, _, reg, job, _ = inputs(tmp_path, monkeypatch, "gru")
    monkeypatch.setattr(capture, "_open_session", lambda *args: pytest.fail("native session created"))
    reg["experiment"]["optimizer_updates"] = 100
    with pytest.raises(ValueError, match="binding"):
        capture.capture_quarantined(tmp_path / "reject", reg, job, config=config,
                                    checkpoint_path=checkpoint)


def test_partial_archive_write_leaves_only_costs_and_error(tmp_path, monkeypatch):
    capture, config, checkpoint, _, reg, job, _ = inputs(tmp_path, monkeypatch, "mlp")

    def interrupted_write(staging, raw, receipt):
        (staging / "episode.json.gz").write_bytes(b"partial")
        raise OSError("injected archive write failure")

    monkeypatch.setattr(capture, "publish_archive", interrupted_write)
    folder = tmp_path / "interrupted"
    with pytest.raises(OSError, match="injected archive write failure"):
        capture.capture_quarantined(folder, reg, job, config=config, checkpoint_path=checkpoint)
    receipt = json.loads((folder / "receipt.json").read_bytes())
    assert receipt["status"] == "error" and receipt["control_cycles"] == 5
    assert "archive_sha256" not in receipt and not (folder / "episode.json.gz").exists()
