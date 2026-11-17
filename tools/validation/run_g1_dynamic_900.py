"""Bounded, zero-update physical qualification at 900 um/s. Default action is a dry run."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "deliverables/learning_chain/g1_dynamic_900_20261105"
HISTORY = ROOT / "deliverables/learning_chain/time_budget_search_batch1_20261103/registration.json"
SOFTWARE = ROOT / "deliverables/learning_chain/switchable_sac_20261105/verification.json"
from tools.validation.run_yaw_pilot import write

MODES = ("mlp", "gru")
# Each block of four is paired by physical case and epsilon tape.
SCHEDULE = (("mlp","P15",2), ("gru","M15",2), ("mlp","M15",2), ("gru","P15",2),
            ("mlp","P15",1), ("gru","M15",1), ("mlp","M15",1), ("gru","P15",1))
MODULE = "tools.validation.run_g1_dynamic_900"


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stamp():
    return datetime.now(timezone.utc).isoformat()


def plan():
    prior = read(HISTORY)
    cases = {j["id"]:j for j in prior["schedule"]}
    rows = []
    for mode, sign, seed_index in SCHEDULE:
        source = cases[f"S900_{sign}_S{seed_index}"]
        rows.append(dict(policy_mode=mode, episode_id=f"{mode.upper()}_{sign}_S{seed_index}",
                         case=source["case"], seed=source["seed"], exploration_seed=source["noise_seed"],
                         deterministic=False, split="qualification", historical_case=source["id"]))
    return rows


def prepare():
    from tools.learning.recovery_learning_contract import experiment_config
    from tools.learning.switchable_sac import Experiment, save_checkpoint
    jobs = plan()
    software = read(SOFTWARE)
    if software["test_results"] != dict(tests=171, errors=0, failures=0, skipped=0):
        raise ValueError("Expected qualified software verification")
    for filename, expected in software["files"].items():
        if sha(ROOT / filename) != expected:
            raise ValueError(f"Changed software evidence: {filename}")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "requests").mkdir()
    (OUT / "run").mkdir()
    common = read(HISTORY)["common"]
    bindings = {}
    for mode in MODES:
        config = experiment_config(mode, search_speed_um_s=900)
        experiment = Experiment(config)
        checkpoint = save_checkpoint(experiment, OUT / "checkpoints" / mode)
        bindings[mode] = dict(config=config, reg=dict(experiment=experiment.archive_binding(checkpoint), common=common))
    pins = {}
    for job in jobs:
        data = bindings[job["policy_mode"]]
        request = OUT / "requests" / (job["episode_id"]+".json")
        write(request, dict(**data, job=job))
        pins[job["episode_id"]] = sha(request)
    sources = [p for p in (ROOT/"tools").rglob("*.py") if p.is_file()]
    sources += [p for p in (ROOT/"models").rglob("*.xml") if p.is_file()]
    frozen = {p.relative_to(ROOT).as_posix():sha(p) for p in sources}
    result = dict(stage="G1", registered_utc=stamp(), schedule=jobs, requests=pins, inputs=frozen,
                  common_sha256=sha(HISTORY), software_sha256=sha(SOFTWARE), max_attempts=8, retries=0,
                  concurrent_physics=1, worker_timeout_s=2400, audit_timeout_s=1500,
                  stop_at_first_unqualified=True, search_speed_um_s=900, passive_yaw_enabled=True,
                  task_deadline_s=30, max_control_cycles=16000, max_physical_substeps_per_attempt=160000,
                  training_updates=0, publish_to_replay=False, previous_initializations=455,
                  decision="Complete both signs and preselected cases unless STOP, invalid episode, audit failure, or worker failure. No extra resets. G2 requires verified full native force recovery and actual resumed SEARCH. Document unobserved branches.")
    write(OUT/"registration.json", result)
    return sha(OUT/"registration.json")


def request_for(identity, expected):
    path = OUT/"registration.json"
    if sha(path) != expected:
        raise ValueError("Registration digest differs")
    reg = read(path)
    if reg["schedule"] != plan() or len(reg["schedule"]) != 8:
        raise ValueError("Schedule differs")
    for rel, value in reg["inputs"].items():
        if sha(ROOT/rel) != value:
            raise ValueError("Frozen source/model differs: "+rel)
    request = OUT/"requests"/(identity+".json")
    if sha(request) != reg["requests"][identity]:
        raise ValueError("Request digest differs")
    return read(request), reg


def worker(action, identity, expected):
    req, reg = request_for(identity, expected)
    job = req["job"]
    checkpoint = OUT/"checkpoints"/job["policy_mode"]
    folder = OUT/"run"/identity
    if action == "capture":
        if (OUT/"STOP").exists():
            raise RuntimeError("Stage stopped")
        from tools.learning.switchable_capture import capture_quarantined
        capture_quarantined(folder, req["reg"], job, config=req["config"], checkpoint_path=checkpoint)
    else:
        from tools.validation.run_consistent_sac import select
        select({"runtime_sha256": req["reg"]["common"]["runtime"]["compatibility_record_sha256"]})
        from tools.validation.recovery_learning_audit import audit_recovery_learning_archive
        _, _, proof = audit_recovery_learning_archive(folder, req["reg"], job, config=req["config"],
                                                     checkpoint_path=checkpoint)
        write(folder/"audit.json", proof)


def supervise(action, identity, pin, timeout):
    work = OUT/"monitor"
    work.mkdir(exist_ok=True)
    with (work/f"{identity}.{action}.log").open("xb") as log:
        cmd = [sys.executable, "-B", "-X", "utf8", "-m", MODULE, action, "--episode", identity,
               "--registration-sha256",pin]
        with subprocess.Popen(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,
                              creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0)) as child:
            start = time.monotonic()
            write(work/"active.json",dict(episode=identity, action=action, pid=child.pid, utc=stamp()))
            while child.poll() is None:
                if (OUT/"STOP").exists() or time.monotonic()-start>timeout:
                    child.kill()
                    child.wait()
                    raise RuntimeError(f"{action} interrupted; preserve partial costs, no retry")
                time.sleep(2)
            if child.returncode:
                raise RuntimeError(f"{identity} {action} exited {child.returncode}")


def launch(pin):
    reg = read(OUT/"registration.json")
    if sha(OUT/"registration.json") != pin:
        raise ValueError("Unregistered batch")
    with (OUT/"launcher.claim").open("x") as stream:
        stream.write(str(os.getpid()))
    ledger = dict(stage="G1", started_utc=stamp(), registration_sha256=pin, attempts=[], status="RUNNING")
    try:
        for job in reg["schedule"]:
            if (OUT/"STOP").exists():
                raise RuntimeError("STOP present")
            identity = job["episode_id"]
            if len(ledger["attempts"]) >= reg["max_attempts"]:
                raise RuntimeError("Attempt ceiling")
            row = dict(episode_id=identity, policy_mode=job["policy_mode"], started_utc=stamp(), status="CAPTURING")
            ledger["attempts"].append(row)
            write(OUT/"ledger.json",ledger)
            supervise("capture",identity,pin,reg["worker_timeout_s"])
            receipt = read(OUT/"run"/identity/"receipt.json")
            row.update(status="AUDITING",outcome=receipt["outcome"], reason=receipt["final_reason"],
                       task_end_s=receipt["task_end_time_s"], initializations=receipt["reset_attempted"])
            write(OUT/"ledger.json",ledger)
            supervise("audit",identity,pin,reg["audit_timeout_s"])
            proof = read(OUT/"run"/identity/"audit.json")
            if not proof["verified"] or proof["optimizer_updates"] or proof["training_admitted"]:
                raise RuntimeError("Unqualified physical archive")
            row.update(status="AUDITED",ended_utc=stamp(), recovery=proof["force_recovery"])
            write(OUT/"ledger.json",ledger)
        ledger["status"]="COMPLETED"
    except BaseException as exc:
        ledger.update(status="STOPPED", error=repr(exc))
        if not (OUT/"STOP").exists():
            write(OUT/"STOP",dict(utc=stamp(),error=repr(exc)))
        raise
    finally:
        ledger["ended_utc"]=stamp()
        write(OUT/"ledger.json",ledger)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("describe","prepare","launch","capture","audit"),default="describe",nargs="?")
    parser.add_argument("--episode", choices=[j["episode_id"] for j in plan()])
    parser.add_argument("--registration-sha256")
    args=parser.parse_args()
    if args.action=="describe":
        print(json.dumps(plan(),indent=2))
    elif args.action=="prepare":
        print(prepare())
    elif args.action=="launch":
        launch(args.registration_sha256)
    else:
        if not args.episode or not args.registration_sha256:
            parser.error("An episode and frozen registration digest are required")
        worker(args.action,args.episode,args.registration_sha256)


if __name__=="__main__":
    main()
