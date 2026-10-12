"""Hard wall supervisor for preparation, execution and audit; no runtime imports."""
import os
from pathlib import Path
import subprocess
import sys
import time
from joint_contract import ROOT,read,sha,write
from windows_job import Job


def enter_gate(base,parent_pid,registered_at):
    sys.path.insert(0,str(ROOT))
    from tools.validation.process_parent import require_registered_parent
    base=Path(base).resolve();pid=int(parent_pid);registered=float(registered_at)
    if not base.is_relative_to(ROOT):raise ValueError('Gate outside registered workspace')
    proof=require_registered_parent(pid,registered)
    write(base.with_suffix('.ready.json'),dict(proof=proof,registered_at=registered))
    deadline=time.monotonic()+30
    while not base.with_suffix('.go.json').exists():
        if time.monotonic()>=deadline:raise TimeoutError('No owned process GO')
        time.sleep(.02)
    expected=dict(pid=os.getpid(),parent_pid=pid,registered_at=registered,job_assigned=True)
    if read(base.with_suffix('.go.json'))!=expected:raise ValueError('Gate identity changed')
    require_registered_parent(pid,registered)


def bounded_process(command,base,timeout,*,job_factory=Job,phase_file=None):
    """Child receives (gate_path, parent_pid, registration_time) and must enter_gate.

    Source hashing, decompression, numerical audit and any resulting children
    run inside this externally timed job, even if their Python code hangs.
    """
    sys.path.insert(0,str(ROOT))
    from tools.validation.process_parent import windows_process,validate_chain
    base=Path(base);base.parent.mkdir(parents=True,exist_ok=True)
    if any(base.with_suffix(s).exists() for s in ('.ready.json','.go.json','.supervisor.json','.log')):
        raise FileExistsError('Gate must be fresh')
    began=time.monotonic();registered=time.time();assigned=False
    receipt=dict(process_exit_confirmed=False,owned_launcher_exit_confirmed=False,go_issued=False,deadline_hit=False)
    with job_factory() as job,base.with_suffix('.log').open('x',encoding='utf-8') as log:
        child=subprocess.Popen([*command,str(base),str(os.getpid()),str(registered)],cwd=ROOT,
            stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            job.assign(child._handle);assigned=True
            ready=base.with_suffix('.ready.json')
            while not ready.exists():
                if time.monotonic()-began>=timeout:raise TimeoutError('Hard deadline before readiness')
                if child.poll() is not None:raise RuntimeError('Guarded child exited before readiness')
                time.sleep(.02)
            record=read(ready);proof=record['proof']
            if record['registered_at']!=registered:raise ValueError('Readiness registration differs')
            with windows_process(proof['pid']) as native,windows_process(os.getpid()) as registered_parent:
                with windows_process(native['parent_pid']) as immediate:
                    validate_chain(expected_pid=os.getpid(),registered_at=registered,now=time.time(),child=native,
                        parent=immediate,registered=registered_parent,python_image=sys._base_executable,launcher_image=command[0])
                    if native!=proof['child']:raise ValueError('Guarded native identity differs')
                    job.assign_pid(native['pid'])
                    if time.monotonic()-began>=timeout:raise TimeoutError('Hard deadline before GO')
                    write(base.with_suffix('.go.json'),dict(pid=native['pid'],parent_pid=os.getpid(),registered_at=registered,job_assigned=True))
                    receipt['go_issued']=True
            while child.poll() is None or job.active():
                if time.monotonic()-began>=timeout:raise TimeoutError('Hard supervised deadline')
                if phase_file is not None and Path(phase_file).exists():
                    phase=read(phase_file)
                    if type(phase.get('limit_s')) is not int or phase['limit_s'] not in (1200,1800) or time.time()-phase['started']>=phase['limit_s']:
                        raise TimeoutError('Hard phase deadline')
                time.sleep(.02)
            receipt.update(process_exit_confirmed=True,owned_launcher_exit_confirmed=True,returncode=child.returncode)
            if child.returncode:raise RuntimeError('Guarded child returned failure; no retry')
            return receipt
        except BaseException as exc:
            receipt.update(error=repr(exc),deadline_hit=isinstance(exc,TimeoutError))
            try:
                job.stop()
                if child.poll() is None and not assigned:child.terminate()  # Own Popen handle, never a reused PID.
                child.wait(timeout=15)
                receipt['owned_launcher_exit_confirmed']=True
                # If initial assignment failed, no GO was issued; descendants
                # have no execution permission, but their tree exit is unknown.
                receipt['process_exit_confirmed']=assigned and job.active()==0
            finally:write(base.with_suffix('.supervisor.json'),dict(receipt,wall_seconds=time.monotonic()-began))
            raise
        finally:
            write(base.with_suffix('.supervisor.json'),dict(receipt,wall_seconds=time.monotonic()-began))
