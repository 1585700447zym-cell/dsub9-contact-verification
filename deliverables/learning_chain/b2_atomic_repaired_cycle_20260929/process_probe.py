"""Real entry identity/claim functions under frozen supervisor, zero physics."""
import importlib.util,json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
os.environ['MPLCONFIGDIR']=str(ROOT/'tmp/learning_mpl_cache')
folder=Path(sys.argv[1]);role=sys.argv[2];scenario=sys.argv[3]
calls=dict(physics=0,optimizer=0,prediction=0)

def guards():
    from tools.learning.runtime import verify_runtime
    verify_runtime(ROOT/'tmp/mujoco_3_13_probe')
    import mujoco,torch
    from tools.learning.sac_update import SACUpdater
    def deny(kind):
        def fail(*a,**kw):calls[kind]+=1;raise AssertionError('Forbidden probe call: '+kind)
        return fail
    torch.optim.Adam.step=deny('optimizer');SACUpdater.predict=deny('prediction')
    for name in ('mj_forward','mj_step','mj_step1','mj_step2','mj_resetData','mj_resetDataKeyframe'):
        setattr(mujoco,name,deny('physics'))

def write(name,r):
    (folder/name).write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')

def command(role):return [sys.executable,'-X','utf8','-B',str(Path(__file__).resolve()),str(folder),role,scenario]

if role=='supervisor':
    driver=ROOT/'deliverables/learning_chain/b2_bounded_cycle_20260927/retry_01/driver.py'
    spec=importlib.util.spec_from_file_location('trusted_probe_supervisor',driver)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    code=module.supervise(command('worker'),folder,ROOT)
    assert (folder/'worker_calls.json').exists(),'Worker call accounting missing'
    if code==0:assert (folder/'restore_calls.json').exists(),'Restore call accounting missing'
    for name in ('worker_calls.json','restore_calls.json'):
        if (folder/name).exists():
            for key,value in json.loads((folder/name).read_text()).items():calls[key]+=value
    write('probe_report.json',dict(scenario=scenario,worker_exit=code,forbidden_call_counts=calls))
else:
    try:
        guards()
        from tools.validation import run_atomic_repaired_cycle as entry
        entry.qualification.DELIVERY=folder
        binding=entry.bound_runner()
        runner=binding.__enter__()
        runner.DELIVERY=folder  # Only fixture output changes; identity check/claim are real.
        if role=='worker' and scenario in ('wrong_parent','stale_registration'):
            r=json.loads((folder/'started.json').read_text())
            if scenario=='wrong_parent':r['supervisor_pid']=os.getpid()
            else:r['wall_timestamp']=1.
            write('started.json',r)
        identity=runner.require_parent(role=='restore')
        write(role+'_identity.json',identity)
        runner.claim(role)
        if role=='worker':
            if scenario=='duplicate_claim':runner.claim(role)
            completed=subprocess.run(command('restore'),cwd=ROOT)
            raise SystemExit(completed.returncode)
    finally:write(role+'_calls.json',calls)
