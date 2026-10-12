"""Prepared reader supervision repair; does not resume the sealed experiment."""
import json
import os
from pathlib import Path
import subprocess
import time


class ReaderFailure(RuntimeError):
    pass


def run_reader(command, cwd, folder, *, timeout_s=300., guard=None):
    if timeout_s <= 0 or timeout_s > 300:
        raise ValueError('Reader wall limit must be in (0, 300] seconds')
    folder=Path(folder)
    folder.mkdir(exist_ok=False)
    started=time.perf_counter();process=None;status='starting';error=None
    def write(name, value):
        with (folder/name).open('w',encoding='utf-8') as stream:
            json.dump(value,stream,ensure_ascii=False,indent=2);stream.flush();os.fsync(stream.fileno())
    write('request.json',dict(command=list(command),cwd=str(cwd),timeout_s=timeout_s,retry=False))
    try:
        if guard is not None:guard()
        with (folder/'stdout.txt').open('w',encoding='utf-8') as stdout, (folder/'stderr.txt').open('w',encoding='utf-8') as stderr:
            process=subprocess.Popen(command,cwd=cwd,stdout=stdout,stderr=stderr,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            write('process.json',dict(pid=process.pid,parent_pid=os.getpid(),wall_timestamp=time.time()))
            while process.poll() is None:
                if guard is not None:guard()
                if time.perf_counter()-started >= timeout_s:
                    status='timeout';break
                time.sleep(.05)
            if status!='timeout':status='finished' if process.returncode==0 else 'failed'
    except BaseException as exc:
        status='supervision_error';error=repr(exc)
    finally:
        cleanup_error=None
        if process is not None and process.poll() is None:
            try:process.kill();process.wait(timeout=10)
            except BaseException as exc:cleanup_error=repr(exc)
        record=dict(status=status,pid=process.pid if process else None,
            returncode=process.poll() if process else None,process_stopped=process is None or process.poll() is not None,
            elapsed_s=time.perf_counter()-started,error=error,cleanup_error=cleanup_error,retry=False)
        write('exit.json',record)
    if status!='finished' or record['returncode']!=0 or not record['process_stopped'] or cleanup_error:
        raise ReaderFailure(json.dumps(record,ensure_ascii=False))
    return dict(record,stdout=(folder/'stdout.txt').read_text(encoding='utf-8'),stderr=(folder/'stderr.txt').read_text(encoding='utf-8'))
