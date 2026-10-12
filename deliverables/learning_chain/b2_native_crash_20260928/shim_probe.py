import ctypes,json,subprocess,sys
from pathlib import Path
from probe import ROOT,HERE,write,native_diagnostics

def worker(kind,out):
    out.mkdir(exist_ok=False);cb=native_diagnostics(out)
    from tools.learning.runtime import verify_runtime
    verify_runtime(ROOT/'tmp/mujoco_3_13_probe')
    import mujoco,numpy as np
    m=mujoco.MjModel.from_binary_path('model.mjb',assets={'model.mjb':(HERE/'model.mjb').read_bytes()})
    d=mujoco.MjData(m);mujoco.mj_setState(m,d,np.load(HERE/'capture_02/pre_forward_state.npy'),mujoco.mjtState.mjSTATE_INTEGRATION)
    mujoco.mj_kinematics(m,d)
    dll=ctypes.CDLL(str(ROOT/'tmp/native_crash_shim_build/Release'/('diagnostic_'+kind+'.dll')))
    f=dll.diagnostic_pair;f.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int,ctypes.c_int];f.restype=ctypes.c_int
    write(out/'started.json',dict(physical_steps=0,optimizer_calls=0,kind=kind))
    overflow=f(m._address,d._address,4736,4450)
    write(out/'result.json',dict(overflow_bytes=overflow,physical_steps=0,optimizer_calls=0))

if __name__=='__main__':
    if sys.argv[1]=='--worker':worker(sys.argv[2],Path(sys.argv[3]))
    else:
        kind=sys.argv[1];name=sys.argv[2]
        with (HERE/(name+'.log')).open('x',encoding='utf-8') as log:
            p=subprocess.run([sys.executable,'-X','utf8','-X','faulthandler','-B',str(Path(__file__).resolve()),'--worker',kind,str(HERE/name)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=30)
        write(HERE/(name+'_exit.json'),dict(returncode=p.returncode,hex=hex(p.returncode&0xffffffff)))
