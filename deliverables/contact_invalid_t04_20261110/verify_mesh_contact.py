"""Fail-closed frozen-pose regression for native mesh contact expansion."""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys


OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
SOURCE = ROOT/"deliverables/learning_chain/load_warning_7pct_gru_short_20261109/run"
WITNESSES = {"T04_GRU":4.580123486, "T04_GRU_RETRY":5.736550785, "T04_GRU_YM200":6.901919925}
NAMES = ("d_socket_female_seg_031","d_guide_male_seg_057")


def file_sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_pose(identity):
    folder=SOURCE/identity
    receipt=json.loads((folder/"receipt.json").read_bytes())
    archive=folder/"episode.json.gz"
    if file_sha(archive)!=receipt["archive_sha256"] or file_sha(folder/"model_used.xml")!=receipt["model_xml_sha256"]:
        raise ValueError("Original frozen input differs")
    with gzip.open(archive,"rb") as stream:
        record=json.load(stream)
    return record["trace"][-1],receipt["model_xml_sha256"]


def query(mujoco, model, frame, pair, dz):
    data=mujoco.MjData(model)
    pose=frame["position_m"]+frame["quaternion_wxyz"]
    pose[2]+=dz
    data.qpos[:]=pose
    mujoco.mj_fwdPosition(model,data)
    if data.time!=0 or data.qpos.tolist()!=pose:
        raise ValueError("Static regression changed pose or time")
    matched=[c for c in data.contact if set(map(int,c.geom))==pair]
    deepest=min(matched,key=lambda c:c.dist) if matched else None
    depth=max(0.,-float(deepest.dist)) if deepest is not None else 0.
    return dict(pair_contacts=len(matched),pair_penetration_m=depth,
                pair_normal_z=float(deepest.frame[2]) if deepest is not None else None,
                full_penetration_m=max((max(0.,-float(c.dist)) for c in data.contact),default=0.),
                all_contacts=int(data.ncon),finite=all(math.isfinite(float(c.dist)) for c in data.contact))


def aligned_mesh_faces(mujoco):
    vertices=" ".join(str(x) for a in (-.001,.001) for b in (-.001,.001) for c in (-.001,.001)
                      for x in (a,b,c))
    model=mujoco.MjModel.from_xml_string(
        f'<mujoco><asset><mesh name="cube" vertex="{vertices}"/></asset><worldbody>'
        '<geom type="mesh" mesh="cube"/><body pos="0 0 .0019"><freejoint/>'
        '<geom type="mesh" mesh="cube"/></body></worldbody></mujoco>')
    result=query(mujoco,model,dict(position_m=[0.,0.,.0019],quaternion_wxyz=[1.,0.,0.,0.]),{0,1},0.)
    result["passes"]=result["finite"] and result["pair_contacts"]>=2 and abs(result["pair_penetration_m"]-.0001)<1e-9
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime",type=Path)
    parser.add_argument("--runtime-sha256")
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    if args.runtime is not None:
        from tools.learning.runtime import select_runtime
        select_runtime(args.runtime,expected_digest=args.runtime_sha256)
    else:
        from tools.validation.run_actor_lr_comparison import select_qualified_runtime
        select_qualified_runtime()
    from tools.learning.runtime import active_package,verify_runtime
    runtime=verify_runtime(active_package())
    import mujoco
    xml=SOURCE/"T04_GRU/model_used.xml"
    model=mujoco.MjModel.from_xml_string(xml.read_text(encoding="utf8"))
    forbidden=int(mujoco.mjtDisableBit.mjDSBL_NATIVECCD)|int(mujoco.mjtDisableBit.mjDSBL_MULTICCD)
    assert not (model.opt.disableflags & forbidden) and model.opt.ccd_tolerance==1e-12
    pair={mujoco.mj_name2id(model,mujoco.mjtObj.mjOBJ_GEOM,name) for name in NAMES}
    if len(pair)!=2 or -1 in pair:
        raise ValueError("Expected two distinct guide and socket geoms")
    results={}
    for identity,expected_nm in WITNESSES.items():
        frame,digest=read_pose(identity)
        assert digest==file_sha(xml)
        shallow=query(mujoco,model,frame,pair,0.)
        separated=query(mujoco,model,frame,pair,-100e-9)
        deep=query(mujoco,model,frame,pair,100e-6)
        good=(shallow["finite"] and shallow["pair_contacts"]>0
              and abs(shallow["pair_penetration_m"]*1e9-expected_nm)<.03
              and abs(shallow["pair_normal_z"])>.999 and shallow["full_penetration_m"]<1e-6
              and separated["finite"] and separated["pair_contacts"]==0
              and deep["finite"] and deep["pair_penetration_m"]>80e-6)
        results[identity]=dict(shallow=shallow,separated=separated,true_deep=deep,passes=good)
        print(identity, "static pass" if good else "static fail",
              shallow["pair_penetration_m"]*1e6,deep["pair_penetration_m"]*1e6,flush=True)
    aligned=aligned_mesh_faces(mujoco)
    print("aligned face contacts",aligned["pair_contacts"],"pass",aligned["passes"],flush=True)
    passed=aligned["passes"] and all(row["passes"] for row in results.values())
    with args.output.open("x",encoding="utf8") as stream:
        json.dump(dict(passed=passed,runtime_sha256=runtime["compatibility_record_sha256"],
                       model_sha256=file_sha(xml),native_and_multiccd_enabled=True,
                       static_queries=10,physical_steps=0,aligned_mesh_faces=aligned,results=results),stream,indent=2)
    return 0 if passed else 1


if __name__=="__main__":
    sys.path.insert(0,str(ROOT))
    raise SystemExit(main())
