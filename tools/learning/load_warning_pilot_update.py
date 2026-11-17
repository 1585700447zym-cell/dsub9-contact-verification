"""Disk-audited admission and bounded optimization for the load-warning pilot."""
from pathlib import Path

from .recovery_learning_contract import SEARCH_ENTRY_FOCUS, protocol_name, validate_config
from .switchable_sac import load_checkpoint, save_checkpoint


def _prepare(config, output_checkpoint):
    config = validate_config(config)
    if protocol_name(config) != "load_warning" and config.get("replay_focus") != SEARCH_ENTRY_FOCUS:
        raise ValueError("The load-warning pilot requires its registered physical protocol")
    output = Path(output_checkpoint)
    if output.exists():
        raise FileExistsError(output)
    return config, output


def admit_episode(folder, request, *, checkpoint_path, output_checkpoint,
                  qualification_path, registration_digest):
    """Audit saved episode bytes, admit once, then save a new complete checkpoint."""
    config, output = _prepare(request["config"], output_checkpoint)
    reg, job = request["reg"], request["job"]
    # Pin the existing native reader before loading the independent audit module.
    # No environment is constructed or stepped by this selection.
    from tools.validation.run_consistent_sac import select
    select({"runtime_sha256": reg["common"]["runtime"]["compatibility_record_sha256"]})
    experiment = load_checkpoint(checkpoint_path, config=config,
                                 expected_digest=reg["experiment"]["source_checkpoint"])
    publication = experiment.publish_training_archive(
        folder, reg, job, checkpoint_path=checkpoint_path, qualification_path=Path(qualification_path),
        expected_registration_digest=registration_digest, include_audit=True)
    audit = publication.pop("audit")
    checkpoint = save_checkpoint(experiment, output)
    return dict(publication=publication, audit=audit, checkpoint_sha256=checkpoint,
                **experiment.training_summary)


def optimize(checkpoint_path, output_checkpoint, *, config, checkpoint_digest,
             target_updates, max_updates, progress=None):
    """Advance to a cumulative target and report attempts separately from saved state.

    Attempted/completed count this invocation. optimizer_updates includes the
    starting checkpoint. An interrupted 'attempting' record is an unconfirmed
    attempt, so its completed count is the confirmed lower bound.
    """
    if progress is not None and not callable(progress):
        raise TypeError("Progress must be a callable or None")
    if (type(target_updates) is not int or type(max_updates) is not int
            or not 0 <= target_updates <= max_updates):
        raise ValueError("Cumulative integer update target must fit the update budget")
    config, output = _prepare(config, output_checkpoint)
    experiment = load_checkpoint(checkpoint_path, config=config, expected_digest=checkpoint_digest)
    if experiment.optimizer_updates > target_updates:
        raise ValueError("Cumulative update target is below the completed update budget")
    experiment._require_approved_replay()
    if len(experiment._replay.episode_ids) < 2:
        raise RuntimeError("At least two complete admitted training episodes are required")
    updates = []
    counters = dict(start_updates=experiment.optimizer_updates, target_updates=target_updates,
                    max_updates=max_updates, attempted=0, completed=0,
                    optimizer_updates=experiment.optimizer_updates, checkpoint_saved=False)
    def report(status):
        counters.update(status=status, optimizer_updates=experiment.optimizer_updates)
        if progress is not None:
            progress(dict(counters))
    try:
        while experiment.optimizer_updates < target_updates:
            counters["attempted"] += 1
            report("attempting")
            experiment.update_from_replay()
            counters["completed"] += 1
            report("update_completed")
            updates.append(dict(experiment._training["updates"][-1]))
        report("saving_checkpoint")
        checkpoint = save_checkpoint(experiment, output)
        counters.update(checkpoint_saved=True, checkpoint_sha256=checkpoint)
        report("checkpoint_saved")
    except BaseException as exc:
        counters["error"] = repr(exc)
        try:
            report("failed")
        except BaseException as reporting_error:
            exc.add_note("Failed to persist optimizer progress: " + repr(reporting_error))
        raise
    return dict(updates=updates, checkpoint_sha256=checkpoint, **experiment.training_summary)
