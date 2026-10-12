"""Own native/venv processes by handles; close kills the complete assigned job.

Win32 structures and semantics: https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects
No process is released to the physical backend before assignment succeeds.
"""
import ctypes as C
from ctypes import wintypes as W
import os
import time


class Basic(C.Structure):
    _fields_=[('process_time',C.c_longlong),('job_time',C.c_longlong),('flags',W.DWORD),
              ('min_working',C.c_size_t),('max_working',C.c_size_t),('active_limit',W.DWORD),
              ('affinity',C.c_size_t),('priority',W.DWORD),('scheduling',W.DWORD)]


class IO(C.Structure):
    _fields_=[(name,C.c_ulonglong) for name in ('read_ops','write_ops','other_ops','read_bytes','write_bytes','other_bytes')]


class Extended(C.Structure):
    _fields_=[('basic',Basic),('io',IO),('process_memory',C.c_size_t),('job_memory',C.c_size_t),
              ('peak_process_memory',C.c_size_t),('peak_job_memory',C.c_size_t)]


class Accounting(C.Structure):
    _fields_=[('user',C.c_longlong),('kernel',C.c_longlong),('period_user',C.c_longlong),
              ('period_kernel',C.c_longlong),('page_faults',W.DWORD),('total',W.DWORD),
              ('active',W.DWORD),('terminated',W.DWORD)]


class Job:
    def __init__(self):
        if os.name!='nt':raise OSError('Windows job supervision required')
        self.api=C.WinDLL('kernel32',use_last_error=True)
        signatures={
            'CreateJobObjectW':([C.c_void_p,W.LPCWSTR],W.HANDLE),
            'SetInformationJobObject':([W.HANDLE,C.c_int,C.c_void_p,W.DWORD],W.BOOL),
            'AssignProcessToJobObject':([W.HANDLE,W.HANDLE],W.BOOL),
            'IsProcessInJob':([W.HANDLE,W.HANDLE,C.POINTER(W.BOOL)],W.BOOL),
            'QueryInformationJobObject':([W.HANDLE,C.c_int,C.c_void_p,W.DWORD,C.c_void_p],W.BOOL),
            'TerminateJobObject':([W.HANDLE,W.UINT],W.BOOL),
            'OpenProcess':([W.DWORD,W.BOOL,W.DWORD],W.HANDLE),
            'CloseHandle':([W.HANDLE],W.BOOL)}
        for name,(args,restype) in signatures.items():
            fn=getattr(self.api,name);fn.argtypes=args;fn.restype=restype
        self.handle=self.api.CreateJobObjectW(None,None)
        if not self.handle:raise C.WinError(C.get_last_error())
        limits=Extended();limits.basic.flags=0x2000  # KILL_ON_JOB_CLOSE; no breakaway.
        if not self.api.SetInformationJobObject(self.handle,9,C.byref(limits),C.sizeof(limits)):
            self.close();raise C.WinError(C.get_last_error())

    def assign(self,handle):
        contained=W.BOOL()
        if not self.api.IsProcessInJob(int(handle),self.handle,C.byref(contained)):
            raise C.WinError(C.get_last_error())
        if contained.value:return
        if not self.api.AssignProcessToJobObject(self.handle,int(handle)):
            raise C.WinError(C.get_last_error())

    def assign_pid(self,pid):
        # Called while the verified worker is blocked at its GO gate. A held
        # handle prevents process identity reuse during assignment.
        handle=self.api.OpenProcess(0x100|0x1|0x1000,False,pid)  # SET_QUOTA | TERMINATE | QUERY_LIMITED_INFORMATION
        if not handle:raise C.WinError(C.get_last_error())
        try:self.assign(handle)
        finally:self.api.CloseHandle(handle)

    def active(self):
        info=Accounting()
        if not self.api.QueryInformationJobObject(self.handle,1,C.byref(info),C.sizeof(info),None):
            raise C.WinError(C.get_last_error())
        return info.active

    def stop(self,timeout=15):
        if not self.api.TerminateJobObject(self.handle,79):raise C.WinError(C.get_last_error())
        deadline=time.monotonic()+timeout
        while self.active():
            if time.monotonic()>=deadline:raise RuntimeError('Job exit unconfirmed; close all quota')
            time.sleep(.02)

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle);self.handle=None

    def __enter__(self):return self
    def __exit__(self,*args):self.close()
