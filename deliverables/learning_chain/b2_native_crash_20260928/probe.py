"""Diagnostic-only reproducer. Never publishes replay or performs SAC updates."""
import ctypes
from ctypes import wintypes as W
import faulthandler
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

def write(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temp, path)

def native_diagnostics(out):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.SetErrorMode(0x0002)
    class Record(ctypes.Structure):
        _fields_ = [('code', W.DWORD), ('flags', W.DWORD), ('record', ctypes.c_void_p),
                    ('address', ctypes.c_void_p), ('count', W.DWORD), ('info', ctypes.c_size_t*15)]
    class Pointers(ctypes.Structure):
        _fields_ = [('record', ctypes.POINTER(Record)), ('context', ctypes.c_void_p)]
    kernel.GetModuleHandleExW.argtypes = [W.DWORD, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    kernel.GetModuleFileNameW.argtypes = [ctypes.c_void_p, W.LPWSTR, W.DWORD]
    callback_type = ctypes.WINFUNCTYPE(W.LONG, ctypes.POINTER(Pointers))
    def handler(p):
        e = p.contents.record.contents
        if e.code == 0xc0000005:
            module = ctypes.c_void_p()
            kernel.GetModuleHandleExW(6, e.address, ctypes.byref(module))
            name = ctypes.create_unicode_buffer(32768)
            kernel.GetModuleFileNameW(module, name, len(name))
            write(out/'native_exception.json', dict(code=hex(e.code), address=hex(e.address),
                module=name.value, module_base=hex(module.value or 0),
                module_offset=hex(e.address-(module.value or 0)),
                operation=int(e.info[0]), target_address=hex(e.info[1])))
        return 0
    callback = callback_type(handler)
    kernel.AddVectoredExceptionHandler.argtypes = [W.ULONG, callback_type]
    kernel.AddVectoredExceptionHandler.restype = ctypes.c_void_p
    handle = kernel.AddVectoredExceptionHandler(1, callback)
    if not handle: raise ctypes.WinError(ctypes.get_last_error())
    return callback

def worker(out):
    out.mkdir(exist_ok=False)
    callback = native_diagnostics(out)
    faulthandler.enable()
    from tools.learning.runtime import verify_runtime
    verify_runtime(ROOT/'tmp/mujoco_3_13_probe')
    import mujoco
    import numpy as np
    from tools.learning.bounded_contact import bounded_config, case_at, SEED
    from tools.learning.admitted_collection import _new_session
    from tools.validation.run_contact_cases import ContactCase
    # Same four uniform float32 actions and seed stream as the failed warmup.
    rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([SEED, 1])))
    session = _new_session(bounded_config())
    session.reset(ContactCase(**case_at('diagnostic_x_pos_100', .0001, 0.)), seed=SEED)
    model = session.env.model
    mujoco.mj_saveModel(model, str(out/'model.mjb'))
    state_spec = mujoco.mjtState.mjSTATE_INTEGRATION
    vector = np.empty(mujoco.mj_stateSize(model, state_spec))
    original = mujoco.mj_forward
    count = 0
    def recorded_forward(m, d):
        nonlocal count
        count += 1
        if d.time >= 3.0:
            mujoco.mj_getState(m, d, vector, state_spec)
            np.save(out/'pre_forward_state.npy', vector)
            write(out/'pre_forward.json', dict(call=count, cycle=cycle+1, time=float(d.time),
                state_spec=int(state_spec), finite_state=bool(np.isfinite(vector).all()),
                ncon=d.ncon, nefc=d.nefc, qpos=d.qpos.tolist(), qvel=d.qvel.tolist(),
                qacc=d.qacc.tolist(), warnings=[int(x.number) for x in d.warning],
                jacobian=int(m.opt.jacobian), cone=int(m.opt.cone), solver=int(m.opt.solver)))
        return original(m, d)
    mujoco.mj_forward = recorded_forward
    write(out/'started.json', dict(pid=os.getpid(), diagnostic_only=True, optimizer_calls=0,
         physical_start=1, cycle_cap=2000, seed=SEED, model_ngeom=model.ngeom))
    for cycle in range(2000):
        action = rng.uniform(-1., 1., 4).astype(np.float32)
        session.prepare_cycle()
        result = session.advance_cycle(action)
        if (cycle+1)%100 == 0:
            write(out/'progress.json', dict(cycles=cycle+1, time=session.env.data.time,
                last_qpos=session.env.data.qpos.tolist()))
        if result.done: break
    write(out/'completed.json', dict(cycles=cycle+1, done=session.done, optimizer_calls=0))

def main():
    if len(sys.argv)>1 and sys.argv[1]=='--worker':
        worker(Path(sys.argv[2])); return
    name = sys.argv[1] if len(sys.argv)>1 else 'capture_02'
    out = HERE/name
    with (HERE/(name+'.log')).open('x', encoding='utf-8') as log:
        cmd=[sys.executable,'-X','utf8','-X','faulthandler','-B',str(Path(__file__).resolve()),'--worker',str(out)]
        result=subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=480)
    write(HERE/(name+'_exit.json'),dict(returncode=result.returncode,hex=hex(result.returncode & 0xffffffff)))

if __name__=='__main__': main()
