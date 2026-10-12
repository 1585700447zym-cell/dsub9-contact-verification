"""Bounded local file-only probe of the failed phase deadline I/O mechanism."""
from pathlib import Path
import concurrent.futures
import datetime
import json
import sys
import threading
import time
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];KIT=OUT.parent/'b2_joint_sac_preparation_20261009'
sys.path.insert(0,str(KIT))
from joint_contract import read,write,sha


def main():
    base=OUT/'diagnostic_work';base.mkdir(exist_ok=False)
    if not base.resolve().is_relative_to(OUT.resolve()):raise ValueError('Probe outside stage folder')
    phase=base/'phase.json';write(phase,dict(i=0,started=time.time(),limit_s=1200))
    stop=threading.Event();started=time.monotonic();events=[];reads=0;writes=0
    def reader():
        nonlocal reads
        while not stop.is_set():
            try:read(phase);reads+=1
            except OSError as e:
                events.append(dict(side='read',type=type(e).__name__,errno=e.errno,winerror=getattr(e,'winerror',None),message=str(e)))
            if time.monotonic()-started>15:stop.set()
    def writer():
        nonlocal writes
        try:
            for i in range(1000):
                if stop.is_set():break
                try:write(phase,dict(i=i,started=time.time(),limit_s=1200));writes+=1
                except OSError as e:
                    events.append(dict(side='write',type=type(e).__name__,errno=e.errno,winerror=getattr(e,'winerror',None),message=str(e)))
                time.sleep(.001)
        finally:stop.set()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(reader);b=pool.submit(writer);a.result();b.result()
    result=dict(probe='concurrent_replacement_and_plain_read',wall_s=time.monotonic()-started,
        read_success=reads,write_success=writes,errors=events,read_permission_errors=sum(e['side']=='read' and e['type']=='PermissionError' for e in events),
        write_permission_errors=sum(e['side']=='write' and e['type']=='PermissionError' for e in events),
        original_launcher_log_sha256=sha(OUT/'launcher.log'),original_supervisor_sha256=sha(OUT/'execution/supervisor.supervisor.json'),
        new_physics=0,new_learning=0,scope='New scratch JSON only. Does not retry any experiment or reopen its counter.')
    write(OUT/'phase_io_probe.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='errors'},ensure_ascii=False))


if __name__=='__main__':main()
