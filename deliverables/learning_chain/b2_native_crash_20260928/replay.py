"""Replay the captured native call, without control cycles or optimizer calls."""
import json
from pathlib import Path
import subprocess
import sys
from probe import ROOT,HERE,write,native_diagnostics

def worker(mode,out):
    out.mkdir(exist_ok=False)
    callback=native_diagnostics(out)
    from tools.learning.runtime import verify_runtime
    verify_runtime(ROOT/'tmp/mujoco_3_13_probe')
    import mujoco
    import numpy as np
    m=mujoco.MjModel.from_binary_path('model.mjb',assets={'model.mjb':(HERE/'model.mjb').read_bytes()})
    if mode=='no_midphase': m.opt.disableflags |= int(mujoco.mjtDisableBit.mjDSBL_MIDPHASE)
    if mode=='no_multiccd': m.opt.disableflags |= int(mujoco.mjtDisableBit.mjDSBL_MULTICCD)
    d=mujoco.MjData(m)
    vector=np.load(HERE/'capture_02/pre_forward_state.npy')
    mujoco.mj_setState(m,d,vector,mujoco.mjtState.mjSTATE_INTEGRATION)
    pairs=[]
    if mode=='scan' or mode.startswith('subset_'):
        allowed=set() if mode=='scan' else {tuple(x) for x in json.loads((HERE/(mode+'.json')).read_text())}
        def filter_pair(m,d,g1,g2):
            key=tuple(sorted((g1,g2)))
            pairs.append(key)
            return int(key not in allowed)
        mujoco.set_mjcb_contactfilter(filter_pair)
    write(out/'started.json',dict(mode=mode,physical_steps=0,optimizer_calls=0,state_finite=bool(np.isfinite(vector).all())))
    if mode in ('forward','no_midphase','no_multiccd','scan') or mode.startswith('subset_'): mujoco.mj_forward(m,d)
    elif mode=='collision':
        mujoco.mj_kinematics(m,d)
        mujoco.mj_comPos(m,d)
        mujoco.mj_collision(m,d)
    else: raise ValueError(mode)
    write(out/'completed.json',dict(ncon=d.ncon,nefc=d.nefc,physical_steps=0,optimizer_calls=0))
    if pairs:
        write(out/'pairs.json',sorted(set(pairs)))
        write(out/'geoms.json',{str(g):mujoco.mj_id2name(m,mujoco.mjtObj.mjOBJ_GEOM,g) for pair in pairs for g in pair})

if __name__=='__main__':
    if sys.argv[1]=='--worker': worker(sys.argv[2],Path(sys.argv[3]))
    else:
        mode=sys.argv[1];name=sys.argv[2];out=HERE/name
        with (HERE/(name+'.log')).open('x',encoding='utf-8') as log:
            p=subprocess.run([sys.executable,'-X','utf8','-X','faulthandler','-B',str(Path(__file__).resolve()),
                '--worker',mode,str(out)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=60)
        write(HERE/(name+'_exit.json'),dict(returncode=p.returncode,hex=hex(p.returncode&0xffffffff)))
