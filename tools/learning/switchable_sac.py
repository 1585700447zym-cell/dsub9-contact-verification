"""One experiment entry for ordinary and recurrent five-axis residual policies."""
import argparse
from copy import deepcopy
from functools import partial
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile

import numpy as np
import torch
from tools.publication.five_axis_policy import tensor_digest

from .five_axis_contract import learning_config
from .recovery_learning_contract import (
    ARCHIVE_VERSION, LOAD_WARNING_PROTOCOLS, MODES, PROTOCOL_VERSIONS, SEARCH_ENTRY_FOCUS,
    digest, experiment_config, physical_projection,
    protocol_name, validate_config,
)

STATE_VERSION = "five_axis_switchable_state_v1"
TRAINING_STATE_VERSION = "five_axis_switchable_training_state_v2"
CHECKPOINT_VERSION = "five_axis_switchable_checkpoint_v1"


def _clip_step(optimizer, args, kwargs, *, report, name):
    parameters = [p for group in optimizer.param_groups for p in group["params"]]
    norm = torch.nn.utils.clip_grad_norm_(parameters, 10.0, error_if_nonfinite=True)
    report[name] = norm.item()


def _episode_digest(arrays):
    hasher = hashlib.sha256()
    for name, value in sorted(arrays.items()):
        hasher.update(digest([name, str(value.dtype), list(value.shape)]).encode())
        hasher.update(value.tobytes())
    return hasher.hexdigest()


def _valid_sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _validate_update_result(result, expected_count):
    digest(result)  # JSON finite-number validation also covers reported gradients.
    if (type(result.get("critic_batches")) is not int or result["critic_batches"] != expected_count
            or type(result.get("batch_rows")) is not int or not 0 < result["batch_rows"] <= 256
            or type(result.get("active_rows")) is not int
            or not 0 <= result["active_rows"] <= result["batch_rows"]):
        raise ValueError("Finite optimizer result with at most 256 learning rows required")


class Experiment:
    """Single owner. Collection, updates and checkpointing use distinct episode boundaries."""

    def __init__(self, config):
        self._config = validate_config(config)
        settings = self._config["learning"]
        self._busy = False
        self._failed = False
        self._checkpoint = None
        self.failed_update_attempts = 0
        self._training = None
        self._approved_replay_state = None
        if self.policy_mode == "mlp":
            from .five_axis_training import FiveAxisTrainer
            numerical = learning_config()
            numerical["learning"] = deepcopy(settings)
            self._mlp = FiveAxisTrainer(numerical)
            self._bind_mlp()
        else:
            from .recurrent_sac import RecurrentUpdater
            from .recurrent_replay import RecurrentReplay
            self._updater = RecurrentUpdater(settings)
            self._replay = RecurrentReplay(capacity=settings["replay_capacity"])
            self._replay_rng = np.random.default_rng(settings["seed"] + 2)

    def _bind_mlp(self):
        self._updater = self._mlp.updater
        self._replay = self._mlp.replay
        self._grad_norms = {}
        for name, optimizer in zip(("critic", "actor", "temperature"), self._updater._optimizers(), strict=True):
            optimizer.register_step_pre_hook(partial(_clip_step, report=self._grad_norms, name=name))

    @property
    def policy_mode(self):
        return self._config["policy_mode"]

    @property
    def config(self):
        return deepcopy(self._config)

    @property
    def actor(self):
        return self._updater.policy.actor if self.policy_mode == "mlp" else self._updater.actor

    @property
    def optimizer_updates(self):
        return self._updater.counts["critic"]

    @property
    def training_summary(self):
        episodes = self._training["episodes"] if self._training is not None else []
        return dict(admitted_episodes=len(episodes),
                    admitted_transitions=sum(row["transitions"] for row in episodes),
                    optimizer_updates=self.optimizer_updates)

    def _require_approved_replay(self):
        if self._training is None or self._approved_replay_state is not self._replay._state:
            raise RuntimeError("Replay provenance is not registered for load-warning training")

    def _validate_training_state(self):
        training = self._training
        if (not isinstance(training, dict) or set(training) != {"episodes", "updates"}
                or not isinstance(training["episodes"], list) or not training["episodes"]
                or not isinstance(training["updates"], list)
                or len(training["updates"]) != self.optimizer_updates):
            raise ValueError("Incomplete training provenance")
        digest(training)
        episodes = {}
        previous_update = 0
        hashes = {"archive_sha256", "registration_sha256", "qualification_sha256",
                  "source_checkpoint_sha256", "job_sha256", "audit_sha256", "replay_sha256"}
        focused = self._config.get("replay_focus") == SEARCH_ENTRY_FOCUS
        fields = hashes | {"episode_id", "transitions", "optimizer_updates"}
        if focused:
            fields |= {"search_entry_focus", "search_entry_focus_sha256"}
            from .search_entry_replay import validate_focus_labels
        for row in training["episodes"]:
            if (not isinstance(row, dict) or set(row) != fields
                    or not isinstance(row["episode_id"], str) or not row["episode_id"]
                    or row["episode_id"] in episodes or not all(_valid_sha(row[k]) for k in hashes)
                    or type(row["transitions"]) is not int or row["transitions"] <= 0
                    or type(row["optimizer_updates"]) is not int
                    or not previous_update <= row["optimizer_updates"] <= self.optimizer_updates):
                raise ValueError("Malformed admitted episode provenance")
            if focused:
                labels = row["search_entry_focus"]
                validate_focus_labels(labels, episode_id=row["episode_id"], transition_count=row["transitions"])
                if digest(labels) != row["search_entry_focus_sha256"]:
                    raise ValueError("Focused replay labels differ from admitted provenance")
            episodes[row["episode_id"]] = row
            previous_update = row["optimizer_updates"]
        if set(self._replay._state.seen) != set(episodes):
            raise ValueError("Replay finalized IDs differ from admitted provenance")
        for key, arrays in self._replay._state.episodes:
            if (key not in episodes or episodes[key]["transitions"] != len(arrays["rewards"])
                    or episodes[key]["replay_sha256"] != _episode_digest(arrays)
                    or arrays["truncated"].any() or not arrays["terminated"][-1].item()):
                raise ValueError("Replay data differs from admitted provenance")
        for count, update in enumerate(training["updates"], 1):
            _validate_update_result(update, count)
            ids = update.get("replay_episode_ids")
            if (type(update.get("admitted_episodes")) is not int
                    or not 2 <= update["admitted_episodes"] <= len(episodes)
                    or type(update.get("optimizer_updates")) is not int or update["optimizer_updates"] != count
                    or not isinstance(ids, list) or any(not isinstance(key, str) for key in ids)
                    or len(ids) < 2 or len(ids) != len(set(ids))):
                raise ValueError("Optimizer update lacks admitted replay provenance")
            eligible = training["episodes"][:update["admitted_episodes"]]
            if (not set(ids).issubset(row["episode_id"] for row in eligible)
                    or any(episodes[key]["optimizer_updates"] >= count for key in ids)
                    or update.get("admitted_transitions") != sum(row["transitions"] for row in eligible)):
                raise ValueError("Optimizer update lacks admitted replay provenance")

    def _require_boundary(self):
        if self._busy or self._failed or self._updater.failed:
            raise RuntimeError("Healthy, idle episode/update boundary required")

    def collect(self, session, case, *, episode_id, checkpoint_id, exploration_seed,
                seed=None, deterministic=False, max_cycles=16000):
        from .recurrent_collection import CyclePolicy, collect_episode
        self._require_boundary()
        protocol = protocol_name(self._config)
        physical = physical_projection(session.contract, self._config["search_speed_um_s"], protocol)
        if physical != self._config["physical_protocol"]:
            raise ValueError("Session physical protocol differs")
        envelope = self.archive_binding(checkpoint_id)
        provider = CyclePolicy(self.policy_mode, self.actor, checkpoint_id=checkpoint_id,
                               exploration_seed=exploration_seed, deterministic=deterministic)
        self._busy = True
        try:
            from .five_axis_collection import CollectionError
            try:
                raw = collect_episode(session, case, provider=provider, episode_id=episode_id,
                                      seed=seed, max_cycles=max_cycles, physical_protocol=protocol)
            except CollectionError as exc:
                exc.archive.update(experiment=envelope, training_admitted=False, valid_for_learning=False)
                raise
            raw["experiment"] = envelope
            return raw
        finally:
            self._busy = False

    def _checkpoint_identity(self, checkpoint_id):
        return (checkpoint_id, self.optimizer_updates, tensor_digest(self.actor.state_dict()))

    def archive_binding(self, checkpoint_id):
        if self._checkpoint is None or self._checkpoint != self._checkpoint_identity(checkpoint_id):
            raise ValueError("Save or load the current behavior weights before recording this checkpoint")
        return dict(version=ARCHIVE_VERSION, config_sha256=digest(self._config),
                    policy_mode=self.policy_mode, source_checkpoint=checkpoint_id,
                    optimizer_updates=self.optimizer_updates,
                    physical_protocol=deepcopy(self._config["physical_protocol"]))

    def publish_training_archive(self, folder, reg, job, *, checkpoint_path, qualification_path,
                                 expected_registration_digest, include_audit=False):
        """Publish one externally approved training job after re-auditing its saved bytes.

        The pilot owns the trusted registration digest and budget, and approves the
        G1 report separately. A collector or a successful episode cannot issue a grant.
        """
        from .recovery_learning_contract import verify_training_registration
        from tools.validation.recovery_learning_audit import audit_recovery_learning_archive

        self._require_boundary()
        tracked = protocol_name(self._config) in LOAD_WARNING_PROTOCOLS
        if type(include_audit) is not bool:
            raise ValueError("Explicit audit-return Boolean required")
        if tracked:
            if self._training is None:
                if len(self._replay) or self._replay._state.seen or self.optimizer_updates:
                    raise RuntimeError("Existing replay/updates lack load-warning provenance")
            else:
                self._require_approved_replay()
        verify_training_registration(reg, job, config=self._config, qualification_path=qualification_path,
                                     expected_digest=expected_registration_digest)
        self.archive_binding(reg["experiment"]["source_checkpoint"])
        if job["episode_id"] in self._replay.episode_ids:
            raise RuntimeError("Training episode already published")
        self._busy = True
        try:
            raw, receipt, proof = audit_recovery_learning_archive(
                folder, reg, job, checkpoint_path=checkpoint_path, config=self._config)
            if proof.get("verified") is not True or proof.get("source_replay_verified") is not True:
                raise ValueError("A complete physical and source audit is required")
            outcome = dict(raw["outcome"], valid_for_learning=True)
            previous = self._replay._state
            try:
                publication = self._replay.publish(job["episode_id"], raw["transitions"],
                                                   training_admitted=True, outcome=outcome)
                if publication["committed"] != len(raw["transitions"]) or not publication["committed"]:
                    raise ValueError("A complete audited episode must be committed")
                if tracked:
                    _, arrays = self._replay._state.episodes[-1]
                    record = dict(episode_id=job["episode_id"], transitions=publication["committed"],
                        archive_sha256=receipt["archive_sha256"], registration_sha256=expected_registration_digest,
                        qualification_sha256=reg["g1_sha256"], source_checkpoint_sha256=reg["experiment"]["source_checkpoint"],
                        job_sha256=digest(job), audit_sha256=digest(proof), replay_sha256=_episode_digest(arrays),
                        optimizer_updates=self.optimizer_updates)
                    if self._config.get("replay_focus") == SEARCH_ENTRY_FOCUS:
                        from .search_entry_replay import build_focus_labels
                        labels = build_focus_labels(raw)
                        record.update(search_entry_focus=labels, search_entry_focus_sha256=digest(labels))
                    training = self._training or dict(episodes=[], updates=[])
                    candidate = dict(episodes=[*training["episodes"], record], updates=training["updates"])
                    digest(candidate)
                result = dict(publication, archive_sha256=receipt["archive_sha256"],
                              registration_sha256=expected_registration_digest)
                if include_audit:
                    result["audit"] = deepcopy(proof)
                if self._config.get("replay_focus") == SEARCH_ENTRY_FOCUS:
                    result["search_entry_focus"] = deepcopy(labels)
            except Exception:
                self._replay._state = previous
                raise
            if tracked:
                self._training = candidate
                self._approved_replay_state = self._replay._state
            return result
        finally:
            self._busy = False

    def update_from_replay(self):
        """One optimizer update at an idle boundary after at least two published episodes."""
        self._require_boundary()
        if protocol_name(self._config) in LOAD_WARNING_PROTOCOLS:
            self._require_approved_replay()
        if len(self._replay.episode_ids) < 2:
            raise RuntimeError("At least two complete admitted training episodes are required")
        result = self._update_from_replay()
        if self._training is not None:
            row = dict(result, **self.training_summary, replay_episode_ids=list(self._replay.episode_ids))
            self._training["updates"].append(row)
        return result

    def _update_from_replay(self):
        """Numerical kernel, also exercised separately on synthetic replay."""
        self._require_boundary()
        if not len(self._replay):
            raise ValueError("An admitted, nonempty replay is required")
        mlp = self.policy_mode == "mlp"
        rng = self._mlp.replay_rng if mlp else self._replay_rng
        saved_rng = deepcopy(rng.bit_generator.state)
        saved_attempts = self._mlp.update_attempts if mlp else None
        saved_updater = self._updater._snapshot()
        saved_history_length = len(self._mlp.history) if mlp else None
        expected_count = self.optimizer_updates + 1
        self._busy = True
        try:
            if mlp:
                self._grad_norms.clear()
                result = self._mlp.update_from_replay()
                result = dict(result, **{f"{name}_grad_norm": self._grad_norms.get(name)
                                         for name in ("critic", "actor", "temperature")})
            else:
                timing = self._config["timing"]
                if self._config.get("replay_focus") == SEARCH_ENTRY_FOCUS and self._training is not None:
                    from .search_entry_replay import sample_focus_sequences
                    labels = {row["episode_id"]: row["search_entry_focus"] for row in self._training["episodes"]}
                    batch, sampling = sample_focus_sequences(self._replay, labels_by_episode=labels,
                        burn_in=timing["burn_in"], learn_steps=timing["learn_steps"], rng=rng)
                    result = dict(self._updater.update(batch), **sampling)
                else:
                    batch = self._replay.sample_sequences(timing["sequences"], timing["burn_in"],
                                                          timing["learn_steps"], rng)
                    result = self._updater.update(batch)
            _validate_update_result(result, expected_count)
            return result
        except Exception:
            self._updater._restore(saved_updater)
            rng.bit_generator.state = saved_rng
            if mlp:
                self._mlp.update_attempts = saved_attempts
                del self._mlp.history[saved_history_length:]
            self._failed = True
            self.failed_update_attempts += 1
            raise
        finally:
            self._busy = False

    def state_dict(self):
        self._require_boundary()
        if self.policy_mode == "mlp":
            components = self._mlp.state_dict()
        else:
            components = dict(updater=self._updater.state_dict(), replay=self._replay.state_dict(),
                              replay_rng=deepcopy(self._replay_rng.bit_generator.state))
        state = dict(version=STATE_VERSION, policy_mode=self.policy_mode,
                     config=self.config, components=components)
        if self._training is not None:
            self._require_approved_replay()
            self._validate_training_state()
            state.update(version=TRAINING_STATE_VERSION, training=deepcopy(self._training))
        return state

    @classmethod
    def from_state(cls, state, config):
        config = validate_config(config)
        if not isinstance(state, dict):
            raise ValueError("Versioned experiment state required")
        tracked = state.get("version") == TRAINING_STATE_VERSION
        fields = {"version", "policy_mode", "config", "components"} | ({"training"} if tracked else set())
        if (set(state) != fields or state["version"] not in (STATE_VERSION, TRAINING_STATE_VERSION)
                or (tracked and protocol_name(config) != "load_warning"
                    and config.get("replay_focus") != SEARCH_ENTRY_FOCUS)
                or state["policy_mode"] != config["policy_mode"]
                or digest(state["config"]) != digest(config)):
            raise ValueError("Matching mode, state version and physical protocol required")
        result = cls(config)
        components = state["components"]
        if result.policy_mode == "mlp":
            result._mlp.load_state_dict(components)
            result._bind_mlp()
        else:
            from .sac_checkpoint import _rng
            if not isinstance(components, dict) or set(components) != {"updater","replay","replay_rng"}:
                raise ValueError("Incomplete recurrent component state")
            result._updater.load_state_dict(components["updater"])
            result._replay.load_state_dict(components["replay"])
            result._replay_rng = _rng(components["replay_rng"])
        if tracked:
            result._training = deepcopy(state["training"])
            result._validate_training_state()
            result._approved_replay_state = result._replay._state
        return result


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def save_checkpoint(experiment, path):
    state = experiment.state_dict()
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=path.parent, prefix=".switchable-") as tmp:
        staging = Path(tmp) / "checkpoint"
        staging.mkdir()
        payload = staging / "state.pt"
        with payload.open("xb") as stream:
            torch.save(state, stream)
            stream.flush()
            os.fsync(stream.fileno())
        manifest = dict(version=CHECKPOINT_VERSION, policy_mode=experiment.policy_mode,
                        config_sha256=digest(experiment.config), state_sha256=_sha(payload.read_bytes()))
        encoded = json.dumps(manifest, sort_keys=True).encode()
        with (staging / "manifest.json").open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        staging.rename(path)
    checkpoint_id = _sha(encoded)
    experiment._checkpoint = experiment._checkpoint_identity(checkpoint_id)
    return checkpoint_id


def load_checkpoint(path, *, config, expected_digest):
    config = validate_config(config)
    path = Path(path)
    encoded = (path / "manifest.json").read_bytes()
    if _sha(encoded) != expected_digest:
        raise ValueError("Checkpoint manifest digest differs")
    manifest = json.loads(encoded)
    if (manifest.get("version") != CHECKPOINT_VERSION or manifest.get("policy_mode") != config["policy_mode"]
            or manifest.get("config_sha256") != digest(config)):
        raise ValueError("Checkpoint mode or experiment configuration differs")
    payload = (path / "state.pt").read_bytes()
    if _sha(payload) != manifest["state_sha256"]:
        raise ValueError("Checkpoint payload digest differs")
    state = torch.load(io.BytesIO(payload), map_location="cpu", weights_only=True)
    experiment = Experiment.from_state(state, config)
    experiment._checkpoint = experiment._checkpoint_identity(expected_digest)
    return experiment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy-mode", choices=MODES, default="mlp")
    parser.add_argument("--physical-protocol", choices=PROTOCOL_VERSIONS, default="load_warning_7pct")
    parser.add_argument("--search-speed", type=int, choices=(450,900), default=900)
    parser.add_argument("--seed", type=int, default=2026092716)
    parser.add_argument("--init-checkpoint", type=Path, help="save fresh parameters at a new path")
    args = parser.parse_args()
    config = experiment_config(args.policy_mode, search_speed_um_s=args.search_speed, seed=args.seed,
                               physical_protocol=args.physical_protocol)
    result = dict(config=config, config_sha256=digest(config), training_admitted=False)
    if args.init_checkpoint:
        result["checkpoint_sha256"] = save_checkpoint(Experiment(config), args.init_checkpoint)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()

