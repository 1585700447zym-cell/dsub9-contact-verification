"""Build an isolated 3.13 candidate with a mesh-manifold direction check."""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
BASE_SOURCE = ROOT/"tmp/mujoco_3_13_horizon_source/src/engine/engine_collision_gjk.c"
BASE_BUILD = ROOT/"tmp/mujoco_3_13_horizon_build"
BASE_RECORD = ROOT/"deliverables/learning_chain/b2_repaired_cycle_v2_20260928/runtime.json"
CANDIDATE = ROOT/"tmp/mujoco_3_13_mesh_contact_runtime_20261110"
EXPECTED_SOURCE = "04e0a707d12d42480ab30e901f34db968b649ef34279028d30b96c0c923078c0"
ANCHOR = "  int i = res[0], j = res[1];\n\n  // recover geom1 matching edge or face"
ADDITION = """  int i = res[0], j = res[1];

  // An incident mesh feature may be orthogonal to the EPA separation direction.
  // Keep the original EPA witness when clipping would use that unrelated face.
  if (obj1->geom_type == mjGEOM_MESH && obj2->geom_type == mjGEOM_MESH) {
    const mjtNum* normal = edgecon1 ? n2 + 3*j : n1 + 3*(edgecon2 ? j : i);
    const mjtNum* epa_normal = edgecon1 ? dir : dir_neg;
    if (dot3(normal, epa_normal) < mjFACE_TOL * norm3(epa_normal)) {
      return;
    }
  }

  // recover geom1 matching edge or face"""


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--msbuild",type=Path,help="Build the preconfigured target directly using the existing dependency libraries")
    args=parser.parse_args()
    original=BASE_SOURCE.read_bytes()
    if sha(original)!=EXPECTED_SOURCE or CANDIDATE.exists() or (OUT/"runtime.json").exists():
        raise ValueError("Expected untouched horizon-fixed source and a fresh candidate path")
    base_record=json.loads(BASE_RECORD.read_bytes())
    base_package=Path(base_record["module_file"]).parent.parent
    for path,value in base_record["files"].items():
        if sha((base_package/path).read_bytes())!=value:
            raise ValueError("Original qualified runtime bytes differ")
    newline="\r\n" if b"\r\n" in original else "\n"
    source=original.decode("utf8").replace("\r\n","\n")
    if source.count(ANCHOR)!=1:
        raise ValueError("Expected a unique mesh manifold expansion site")
    patched=source.replace(ANCHOR,ADDITION)
    patched_bytes=patched.replace("\n",newline).encode("utf8")
    diff="".join(difflib.unified_diff(source.splitlines(keepends=True),patched.splitlines(keepends=True),
             fromfile="a/src/engine/engine_collision_gjk.c",tofile="b/src/engine/engine_collision_gjk.c"))
    (OUT/"mesh_multicontact_normal.patch").write_text(diff,encoding="utf8",newline="\n")
    if args.msbuild is None:
        build_log=OUT/"build.log"
        command=["cmake","--build",str(BASE_BUILD),"--config","Release","--target","mujoco","--parallel","4"]
    else:
        build_log=OUT/"build_direct.log"
        command=[str(args.msbuild),str(BASE_BUILD/"mujoco.vcxproj"),"/p:Configuration=Release",
                 "/p:Platform=x64","/p:BuildProjectReferences=false","/p:TrackFileAccess=false","/nr:false","/v:m"]
    task_temp=ROOT/"tmp/mesh_contact_build_temp_20261110"
    task_temp.mkdir(exist_ok=True)
    env=dict(os.environ,TMP=str(task_temp),TEMP=str(task_temp))
    try:
        BASE_SOURCE.write_bytes(patched_bytes)
        with build_log.open("xb") as stream:
            subprocess.run(command,check=True,cwd=BASE_BUILD,env=env,
                           stdout=stream,stderr=subprocess.STDOUT,timeout=600)
    finally:
        BASE_SOURCE.write_bytes(original)
    dll=BASE_BUILD/"bin/Release/mujoco.dll"
    candidate_dll=dll.read_bytes()
    if sha(candidate_dll)==base_record["files"]["mujoco/mujoco.dll"]:
        raise ValueError("Candidate build did not change the DLL")
    shutil.copytree(base_package/"mujoco",CANDIDATE/"mujoco",ignore=shutil.ignore_patterns("__pycache__","*.pyc"))
    (CANDIDATE/"mujoco/mujoco.dll").write_bytes(candidate_dll)
    files={p.relative_to(CANDIDATE).as_posix():sha(p.read_bytes()) for p in sorted((CANDIDATE/"mujoco").rglob("*")) if p.is_file()}
    if (set(files)!=set(base_record["files"]) or
            {key for key in files if files[key]!=base_record["files"][key]}!={"mujoco/mujoco.dll"}):
        raise ValueError("Candidate package changed beyond the intended engine DLL")
    record=dict(version=base_record["version"],module_file=str(CANDIDATE/"mujoco/__init__.py"),files=files,
        base_runtime_sha256=sha(BASE_RECORD.read_bytes()),base_source_sha256=sha(original),
        candidate_source_sha256=sha(patched_bytes),patch_sha256=sha((OUT/"mesh_multicontact_normal.patch").read_bytes()),
        candidate_dll_sha256=sha(candidate_dll),training_admitted=False)
    (OUT/"runtime.json").write_text(json.dumps(record,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    print("runtime",sha((OUT/"runtime.json").read_bytes()),"DLL",record["candidate_dll_sha256"],flush=True)


if __name__=="__main__":
    main()
