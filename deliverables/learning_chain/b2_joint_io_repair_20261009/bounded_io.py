"""Bounded Windows sharing retries for files, never for experiment operations."""
import errno
import json
import math
import os
from pathlib import Path
import time
import uuid

IO_LIMIT_S=.5

def bounded_end(deadline):
    if deadline is not None and (type(deadline) not in (int,float) or not math.isfinite(deadline)):
        raise ValueError('Finite absolute monotonic deadline required')
    end=time.monotonic()+IO_LIMIT_S
    return min(end,deadline) if deadline is not None else end

def check_time(end):
    if time.monotonic()>=end:raise TimeoutError('File I/O deadline; no experiment operation retried')

def retry_io(operation,*,deadline=None):
    end=bounded_end(deadline);delay=.002
    while True:
        check_time(end)
        try:result=operation()
        except PermissionError as exc:
            code=getattr(exc,'winerror',None)
            if os.name!='nt' or not (code in (5,32,33) or (code is None and exc.errno==errno.EACCES)):
                raise
            remaining=end-time.monotonic()
            if remaining<=0:raise TimeoutError('Persistent file sharing denial; deadline reached') from exc
            time.sleep(min(delay,remaining));delay=min(.05,delay*2)
        else:
            check_time(end)
            return result

def read(path,*,deadline=None):
    end=bounded_end(deadline)
    data=retry_io(lambda:Path(path).read_text(encoding='utf8'),deadline=end)
    result=json.loads(data,parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))
    check_time(end)
    return result

def write(path,value,*,deadline=None):
    end=bounded_end(deadline);check_time(end)
    content=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.tmp-'+uuid.uuid4().hex)
    # Serialize and fsync once. Only replace is retried; a final failure retains tmp.
    check_time(end)
    with tmp.open('x',encoding='utf8') as f:
        f.write(content);f.flush();os.fsync(f.fileno())
    retry_io(lambda:os.replace(tmp,path),deadline=end)
