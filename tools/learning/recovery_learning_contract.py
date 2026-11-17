"""Mode selection for the common 100 nm recovery experiment."""
import hashlib
import json
from pathlib import Path

from .five_axis_contract import learning_config

VERSION = "five_axis_recovery_policy_v1"
LOAD_WARNING_VERSION = "five_axis_load_warning_policy_v1"
LOAD_WARNING_PROTOCOLS = ("load_warning", "load_warning_7pct", "load_warning_7pct_mesh_contact")
SEARCH_ENTRY_FOCUS = "search_entry_event_half_v1"
PROTOCOL_VERSIONS = {"recovery": VERSION, "load_warning": LOAD_WARNING_VERSION,
                     "load_warning_7pct": "five_axis_load_warning_search_authority_policy_v2",
                     "load_warning_7pct_mesh_contact": "five_axis_load_warning_mesh_contact_policy_v3"}
MODES = ("mlp", "gru")
ARCHIVE_VERSION = "recovery_cycle_experiment_archive_v1"
CONFIG_DIR = (Path(__file__).resolve().parents[2] / "deliverables/learning_chain"
              / "nano100_force_recovery_20261104")
DIAGNOSTIC_DIGEST = {
    450: "08348e66dd911c4cbe43ee8d9afa3bace3c904109a015248d579f57155a95736",
    900: "437a104f2cec80b411a3c66e7edb794719c462c0cbe42f92911dade01cbb110c",
}
SOURCE_ONLY = {"source_policy", "frozen_policy_compatibility", "optimizer_updates", "replay_publication"}


def digest(value):
    encoded = json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def protocol_name(config):
    for name, version in PROTOCOL_VERSIONS.items():
        if config["version"] == version:
            return name
    raise ValueError("Unknown physical experiment version")


def trial_module(physical_protocol):
    if physical_protocol == "recovery":
        from . import force_recovery_trial
        return force_recovery_trial
    if physical_protocol == "load_warning":
        from . import load_warning_trial
        return load_warning_trial
    if physical_protocol == "load_warning_7pct":
        from . import load_warning_search_authority
        return load_warning_search_authority
    if physical_protocol == "load_warning_7pct_mesh_contact":
        from . import load_warning_mesh_contact_trial
        return load_warning_mesh_contact_trial
    raise ValueError("Unknown physical protocol")


def physical_projection(protocol, speed, physical_protocol="recovery"):
    if type(speed) is not int or speed not in DIAGNOSTIC_DIGEST:
        raise ValueError("Expected an integer search speed of 450 or 900 um/s")
    if physical_protocol == "recovery":
        expected = DIAGNOSTIC_DIGEST[speed]
    else:
        expected = digest(trial_module(physical_protocol).protocol_config(speed))
    if digest(protocol) != expected:
        raise ValueError("Session does not match the registered physical and observation schema")
    return {key: value for key, value in protocol.items() if key not in SOURCE_ONLY}


def experiment_config(policy_mode="mlp", *, search_speed_um_s=900, seed=2026092716,
                      physical_protocol="recovery", focus_search_entry=False):
    if policy_mode not in MODES or type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError("Expected policy_mode mlp/gru and a uint32 seed")
    if type(search_speed_um_s) is not int or search_speed_um_s not in DIAGNOSTIC_DIGEST:
        raise ValueError("Expected 450 or 900 um/s")
    if type(focus_search_entry) is not bool or (focus_search_entry and
            (policy_mode != "gru" or physical_protocol not in ("load_warning_7pct", "load_warning_7pct_mesh_contact"))):
        raise ValueError("Focused replay is registered only for SEARCH authority GRU")
    if physical_protocol == "recovery":
        protocol = json.loads((CONFIG_DIR / f"config_{search_speed_um_s}.json").read_bytes())
    else:
        protocol = trial_module(physical_protocol).protocol_config(search_speed_um_s)
    learning = learning_config()["learning"]
    learning["seed"] = seed
    config = dict(version=PROTOCOL_VERSIONS[physical_protocol], policy_mode=policy_mode, search_speed_um_s=search_speed_um_s,
                physical_protocol=physical_projection(protocol, search_speed_um_s, physical_protocol),
                geometry_tolerance_m=1e-7, learning=learning,
                timing=dict(burn_in=256, learn_steps=128, sequences=2),
                gru_hidden=64, gradient_norm_limit=10.0, task_budget_s=30.0)
    if focus_search_entry:
        config["replay_focus"] = SEARCH_ENTRY_FOCUS
    return config


def validate_config(config):
    try:
        expected = experiment_config(config["policy_mode"], search_speed_um_s=config["search_speed_um_s"],
                                     seed=config["learning"]["seed"], physical_protocol=protocol_name(config),
                                     focus_search_entry="replay_focus" in config)
        if digest(config) != digest(expected):
            raise ValueError("Experiment configuration differs from the registered mode/protocol")
    except (KeyError, TypeError) as exc:
        raise ValueError("Complete versioned experiment configuration required") from exc
    return expected


def verify_training_registration(reg, job, *, config, qualification_path, expected_digest):
    """Bind a preselected training job and a reviewed physical G1 proof to external approval."""
    config = validate_config(config)
    protocol = protocol_name(config)
    focused = config.get("replay_focus") == SEARCH_ENTRY_FOCUS
    if protocol == "load_warning_7pct_mesh_contact" and not focused:
        raise ValueError("Mesh contact runtime requires separate dynamic training qualification")
    if protocol == "load_warning_7pct" and not focused:
        raise ValueError("SEARCH authority protocol requires new dynamic training qualification")
    warning_only = protocol in LOAD_WARNING_PROTOCOLS
    if warning_only and reg.get("stage") != "G2":
        raise ValueError("Training under the load-warning protocol is not registered")
    if digest(reg) != expected_digest or reg.get("stage") != "G2":
        raise ValueError("Trusted training registration required")
    if (job.get("split") != "train" or job.get("deterministic") is not False
            or digest(job) not in reg.get("training_jobs", [])):
        raise ValueError("Only a pre-registered training job may publish")
    report_bytes = Path(qualification_path).read_bytes()
    if hashlib.sha256(report_bytes).hexdigest() != reg.get("g1_sha256"):
        raise ValueError("G1 qualification file differs from registration")
    proof = json.loads(report_bytes)
    if warning_only:
        if protocol == "load_warning_7pct_mesh_contact":
            from tools.validation.load_warning_mesh_contact_qualification import (
                verify_mesh_contact_qualification, verify_mesh_contact_training_job,
            )
            verify_mesh_contact_qualification(proof, config=config)
            verify_mesh_contact_training_job(job, proof=proof)
        elif focused:
            from tools.validation.load_warning_search_qualification import (
                verify_search_authority_qualification, verify_search_authority_training_job,
            )
            verify_search_authority_qualification(proof, config=config)
            verify_search_authority_training_job(job, proof=proof)
        else:
            from tools.validation.load_warning_training_admission import verify_load_warning_qualification
            verify_load_warning_qualification(proof, config=config)
        binding = reg.get("experiment", {})
        if (reg.get("common") != proof["common"]
                or binding.get("config_sha256") != digest(config)
                or binding.get("policy_mode") != config["policy_mode"]
                or binding.get("physical_protocol") != config["physical_protocol"]
                or job.get("episode_id") in proof["qualified_episode_ids"]):
            raise ValueError("New training registration must match the qualified physical domain and use fresh episodes")
        return
    recovery = proof.get("force_recovery", {})
    yaw = proof.get("passive_channel", {})
    # The G1 reviewer registers the source-audited episode which actually
    # demonstrated unload, physical retraction, stability and resumed search.
    if (any(proof.get(key) is not True for key in
            ("verified", "native_reference_verified", "source_replay_verified"))
            or proof.get("physical_protocol_sha256") != digest(config["physical_protocol"])
            or yaw.get("verified") is not True or yaw.get("passive_yaw_enabled") is not True
            or type(yaw.get("recurrence_updates_checked")) is not int or yaw["recurrence_updates_checked"] < 1
            or recovery.get("verified") is not True
            or type(recovery.get("completed_force_recovery_count")) is not int
            or recovery["completed_force_recovery_count"] < 1):
        raise ValueError("G1 proof must show a verified complete force recovery under this protocol")

