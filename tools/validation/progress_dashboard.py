"""Loopback-only, read-only progress view; no learning or physics imports."""
import argparse
from contextlib import contextmanager
import ctypes
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import io
import math
import os
from pathlib import Path
import time


@contextmanager
def shared_reader(path):
    if os.name!='nt':
        with open(path,'rb') as stream:yield stream
        return
    import msvcrt
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    create=kernel.CreateFileW
    create.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,
                    wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
    create.restype=wintypes.HANDLE
    close=kernel.CloseHandle;close.argtypes=[wintypes.HANDLE];close.restype=wintypes.BOOL
    handle=create(str(Path(path).resolve()),0x80000000,7,None,3,0x80,None)
    if handle==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
    try:fd=msvcrt.open_osfhandle(handle,os.O_RDONLY|os.O_BINARY)
    except BaseException:close(handle);raise
    # Release the OS handle before parsing/rendering. MoveFileEx replacement
    # can still reject an open target even with delete sharing on this host.
    with os.fdopen(fd,'rb') as stream:data=stream.read(16*1024*1024+1)
    with io.BytesIO(data) as detached:yield detached


def snapshot(package):
    package=Path(package);warnings=[]
    def read(name,default=None):
        try:
            with shared_reader(package/name) as f:data=f.read(16*1024*1024+1)
            if len(data)>16*1024*1024:raise ValueError('File too large')
            return json.loads(data.decode('utf-8-sig'))
        except FileNotFoundError:return default
        except (OSError,ValueError) as exc:
            warnings.append(name+': '+type(exc).__name__);return default
    progress=read('run/progress.json',{})
    ledger=read('run/ledger.json',{})
    budget=read('run/training_episodes/update_budget.json',{})
    failure=read('run/failure.json');controlled=read('run/controlled_stop.json')
    exit_record=read('process_exit.json');completed=read('run/completed.json')
    started=read('started.json');auth=read('authorization.json',{})
    state='waiting'
    if failure or ledger.get('status')=='failed':state='failed'
    elif controlled:state='stopped'
    elif exit_record is not None:
        state='complete' if exit_record.get('returncode')==0 and completed else 'failed'
    elif started is not None:state='running'
    elif auth.get('approved'):state='ready'
    history=read('run/training/updates.json',[])
    if not history and state=='failed':history=read('run/training_episodes/failure.json',{}).get('history',[])
    loss=[]
    for row in history:
        x=row.get('critic_batches');y=row.get('critic_loss')
        if type(x) in (int,float) and type(y) in (int,float) and math.isfinite(x) and math.isfinite(y):loss.append([x,y])
    if len(loss)>180:loss=loss[::max(1,len(loss)//180)]+[loss[-1]]
    attempts=[]
    for row in ledger.get('attempts',[]):
        r=row.get('result',{})
        attempts.append(dict(stage=row.get('stage'),id=row.get('id'),status=row.get('status'),
            success=r.get('success'),outcome=r.get('task_outcome'),cycles=r.get('cycles'),
            xy_um=r['final_xy_error_m']*1e6 if isinstance(r.get('final_xy_error_m'),(int,float)) else None))
    return dict(state=state,progress=progress,updates=budget.get('completed',progress.get('updates')),
        dynamic_starts=ledger.get('dynamic_starts'),attempts=attempts,loss=loss,
        cumulative=read('run/cumulative_budget.json',{}),authorized_budget=auth.get('budget',{}),
        error=(failure or {}).get('underlying_failure',failure or {}).get('error'),
        stop_reason=(controlled or {}).get('reason'),read_warnings=warnings,served_at=time.time(),
        package=package.name,independent_results=read('run/completed.json',{}).get('independent'))


def handler_for(package,html):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            if self.path in ('/','/index.html'):body=Path(html).read_bytes();kind='text/html; charset=utf-8'
            elif self.path=='/api/status':
                body=json.dumps(snapshot(package),ensure_ascii=False,allow_nan=False).encode('utf-8');kind='application/json; charset=utf-8'
            else:self.send_error(404);return
            self.send_response(200);self.send_header('Content-Type',kind)
            self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)))
            self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(body)
    return Handler


def main():
    p=argparse.ArgumentParser();p.add_argument('--package',type=Path,required=True)
    p.add_argument('--html',type=Path,required=True);p.add_argument('--port',type=int,default=8766)
    args=p.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),handler_for(args.package.resolve(),args.html.resolve()))
    print(f'http://127.0.0.1:{server.server_port}',flush=True)
    server.serve_forever()


if __name__=='__main__':main()
