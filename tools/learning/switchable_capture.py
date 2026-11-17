"""Persist one quarantined MLP/GRU episode from an independently pinned capture request."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.validation.run_yaw_pilot import actual_common, model_archive_bytes, publish_archive, write
from .five_axis_collection import CollectionError
from .five_axis_preparation import COMMON
from .recovery_learning_contract import LOAD_WARNING_PROTOCOLS, digest, protocol_name, trial_module, validate_config
from .switchable_sac import load_checkpoint


def _open_session(config, reg, job):
    # Select the pinned package before importing modules that load native code.
    from tools.validation.run_consistent_sac import select
    runtime = select({"runtime_sha256": reg["common"]["runtime"]["compatibility_record_sha256"]})
    from tools.learning.newton_profile import build_model_xml
    from tools.validation.yaw_pilot import YawContactCase

    case = YawContactCase(**job["case"])
    trial = trial_module(protocol_name(config))
    env = trial.environment_class()()
    model = model_archive_bytes(build_model_xml(env.profile))
    session = trial.session_class(config["search_speed_um_s"])(env)
    return session, case, model, actual_common(env, runtime, model)


def _persist(folder, raw, receipt):
    # Keep the cost receipt, even if encoding fails or the episode cannot be renamed.
    write(folder / "receipt.json", dict(receipt, status="archiving"))
    archive_receipt = receipt.copy()
    with TemporaryDirectory(dir=folder, prefix=".archive-") as staging:
        staging = Path(staging)
        publish_archive(staging, raw, archive_receipt)
        (staging / "episode.json.gz").rename(folder / "episode.json.gz")
    receipt.update(archive_receipt)
    write(folder / "receipt.json", receipt)


def _finish_receipt(receipt, raw, session, physical_protocol):
    cost, evidence, outcome = raw["cost"], raw["evidence"], raw["outcome"]
    receipt.update(reset_attempted=cost["initialization_attempts"],
                   reset_completed=cost["initializations_completed"], physical_substeps=cost["physical_substeps"],
                   control_cycles=evidence["control_cycles_completed"] if cost["initializations_completed"] else None,
                   source_counts=raw["source_counts"], valid=outcome["simulation_valid"],
                   stopped=outcome["physical_stopped"], outcome=outcome["task_outcome"],
                   elapsed_wall_s=cost["wall_time_s"], error=raw.get("error"))
    if cost["initializations_completed"]:
        for field in ("guard_facts", "stop_time_s", "task_end_time_s", "audit_end_time_s", "cumulative_peaks"):
            receipt[field] = evidence.get(field)
        field = "load_warnings" if physical_protocol in LOAD_WARNING_PROTOCOLS else "force_recovery"
        receipt[field] = evidence.get(field)
        receipt["reference_checks"] = getattr(session.env, "reference_checks", None)
    if not raw.get("error"):
        receipt.update(controller_config=asdict(session.controller.config), finish_criteria=session.finish_criteria,
                       final_reason=session.reason)
    receipt["status"] = "error" if raw.get("error") else "finished"


def capture_quarantined(folder, reg, job, *, config, checkpoint_path):
    """Collect one externally specified job. This function never audits, admits or updates."""
    config = validate_config(config)
    if ("execution_contract" in reg or set(reg["common"]) != set(COMMON)
            or type(job["deterministic"]) is not bool or type(job["seed"]) is not int
            or type(job["exploration_seed"]) is not int or job["exploration_seed"] < 0
            or job["seed"] < 0 or not isinstance(job["episode_id"], str)
            or not job["episode_id"].strip()):
        raise ValueError("Complete registered native domain and capture job required")
    pin = reg["experiment"]["source_checkpoint"]
    experiment = load_checkpoint(checkpoint_path, config=config, expected_digest=pin)
    binding = experiment.archive_binding(pin)
    if digest(binding) != digest(reg["experiment"]):
        raise ValueError("Registered experiment binding differs from restored checkpoint")

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    receipt = dict(case=job["case"], seed=job["seed"], episode_id=job["episode_id"],
                   exploration_seed=job["exploration_seed"], deterministic=job["deterministic"],
                   experiment=binding, source_checkpoint_sha256=pin, status="initializing",
                   reset_attempted=0, reset_completed=0, physical_substeps=0, control_cycles=0,
                   valid=False, stopped=False, training_updates=0, training_admitted=False,
                   valid_for_learning=False)
    receipt_path = folder / "receipt.json"
    write(receipt_path, receipt)
    raw = None
    try:
        session, case, model, common = _open_session(config, reg, job)
        if (digest(common) != digest(reg["common"])
                or hashlib.sha256(model).hexdigest() != common["model_xml_sha256"]
                or digest(asdict(case)) != digest(job["case"])):
            raise ValueError("Observed native domain, model or initial case differs from registration")
        with (folder / "model_used.xml").open("xb") as stream:
            stream.write(model)
        receipt.update(common)
        # A process interrupted inside collect may have consumed physics; costs are unknown until frozen.
        receipt.update(status="collecting", reset_attempted=None, reset_completed=None,
                       physical_substeps=None, control_cycles=None)
        write(receipt_path, receipt)
        try:
            raw = experiment.collect(session, case, checkpoint_id=pin, episode_id=job["episode_id"],
                                     exploration_seed=job["exploration_seed"], seed=job["seed"],
                                     deterministic=job["deterministic"])
        except CollectionError as exc:
            raw = exc.archive
            raise
        finally:
            if raw is not None:
                try:
                    _finish_receipt(receipt, raw, session, protocol_name(config))
                finally:
                    _persist(folder, raw, receipt)
    except Exception as exc:
        receipt.update(status="error", error=repr(exc))
        write(receipt_path, receipt)
        raise
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, type=Path, help="JSON with config, reg and job")
    parser.add_argument("--request-sha256", required=True, help="trusted SHA-256 of the request bytes")
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="new quarantine directory")
    args = parser.parse_args()
    encoded = args.request.read_bytes()
    if hashlib.sha256(encoded).hexdigest() != args.request_sha256:
        raise ValueError("Capture request SHA-256 differs")
    request = json.loads(encoded)
    receipt = capture_quarantined(args.output, request["reg"], request["job"],
                                  config=request["config"], checkpoint_path=args.checkpoint)
    print(json.dumps(dict(episode_id=receipt["episode_id"], archive_sha256=receipt["archive_sha256"],
                          training_admitted=False)))


if __name__ == "__main__":
    main()
