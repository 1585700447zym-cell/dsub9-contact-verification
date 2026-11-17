"""One full T04 regression using the original actor and seeds on the new runtime."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys


OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
PRIOR=ROOT/"deliverables/learning_chain/load_warning_7pct_gru_short_20261109"
REQUEST=OUT/"t04_repair_request.json"
DEST=OUT/"T04_contact_fixed"
PROTOCOL="load_warning_7pct_mesh_contact"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def write(path, value):
    with path.open("x",encoding="utf8") as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)


def prepare():
    from tools.learning.recovery_learning_contract import experiment_config
    from tools.learning.switchable_sac import Experiment,load_checkpoint,save_checkpoint,tensor_digest
    from tools.validation.run_consistent_sac import select

    red, green=read(OUT/"frozen_before.json"),read(OUT/"frozen_after.json")
    if red["passed"] or not green["passed"] or green["runtime_sha256"]!=sha(OUT/"runtime.json"):
        raise ValueError("Verified frozen failure and candidate correction required before a rollout")
    if REQUEST.exists() or DEST.exists():
        raise FileExistsError("T04 verification was already prepared")
    previous=read(PRIOR/"registration.json")
    original=read(PRIOR/"requests/T04_GRU.capture.json")
    orig_job, orig_source=original["job"], original["source"]
    expected,=[job for job in previous["train"] if job["episode_id"]=="T04_GRU"]
    if orig_job!=expected or orig_source["optimizer_updates"]!=0:
        raise ValueError("Original T04 seed or behavior binding differs")
    old=load_checkpoint(PRIOR/orig_source["path"],config=previous["config"],expected_digest=orig_source["checkpoint_sha256"])
    config=experiment_config("gru",seed=previous["config"]["learning"]["seed"],physical_protocol=PROTOCOL)
    if config["learning"]!=previous["config"]["learning"] or config["timing"]!=previous["config"]["timing"]:
        raise ValueError("Unexpected actor architecture or learning configuration change")
    fixed=Experiment(config)
    fixed.actor.load_state_dict(old.actor.state_dict(),strict=True)
    actor_sha=tensor_digest(old.actor.state_dict())
    if (tensor_digest(fixed.actor.state_dict())!=actor_sha or fixed.optimizer_updates
            or fixed._replay.episode_ids):
        raise ValueError("Expected identical actor and fresh diagnostic replay state")
    checkpoint=OUT/"T04_actor_only"
    pin=save_checkpoint(fixed,checkpoint)
    common=deepcopy(previous["common"])
    common["runtime"]=select(dict(runtime_sha256=config["physical_protocol"]["collision_runtime_sha256"]))
    job=dict(orig_job,episode_id="T04_contact_fixed",split="diagnostic")
    reg=dict(common=common,experiment=fixed.archive_binding(pin))
    write(REQUEST,dict(config=config,reg=reg,job=job,checkpoint=checkpoint.relative_to(OUT).as_posix(),
        actor_sha256=actor_sha,source_checkpoint_sha256=orig_source["checkpoint_sha256"],
        original_request_sha256=sha(PRIOR/"requests/T04_GRU.capture.json"),
        static_candidate_sha256=sha(OUT/"frozen_after.json"),max_attempts=1,training_admitted=False))
    print("registered",sha(REQUEST),flush=True)


def run(action,pin):
    if sha(REQUEST)!=pin:
        raise ValueError("T04 verification request changed")
    req=read(REQUEST)
    cfg,reg,job=req["config"],req["reg"],req["job"]
    checkpoint=OUT/req["checkpoint"]
    if action=="capture":
        from tools.learning.switchable_capture import capture_quarantined
        rec=capture_quarantined(DEST,reg,job,config=cfg,checkpoint_path=checkpoint)
        print(rec["outcome"],rec["final_reason"],rec["physical_substeps"],flush=True)
        return
    from tools.validation.run_consistent_sac import select
    select({"runtime_sha256":reg["common"]["runtime"]["compatibility_record_sha256"]})
    from tools.validation.recovery_learning_audit import audit_recovery_learning_archive
    _, rec, proof=audit_recovery_learning_archive(DEST,reg,job,checkpoint_path=checkpoint,config=cfg)
    if (rec["reset_attempted"]!=1 or not proof["verified"] or not proof["source_replay_verified"]
            or proof["optimizer_updates"] or proof["training_admitted"]):
        raise ValueError("T04 verification must be an audited zero-update diagnostic")
    write(DEST/"audit.json",proof)
    print("audited",proof["task_outcome"],flush=True)


if __name__=="__main__":
    sys.path.insert(0,str(ROOT))
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("prepare","capture","audit"))
    parser.add_argument("--pin")
    args=parser.parse_args()
    prepare() if args.action=="prepare" else run(args.action,args.pin)
