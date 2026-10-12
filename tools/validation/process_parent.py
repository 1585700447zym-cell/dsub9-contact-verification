"""Recognize a live registered Python parent through at most one venv launcher."""
from contextlib import contextmanager,ExitStack
import ctypes
from ctypes import wintypes
import math,os,sys,time


def same_image(left,right):
    return os.path.normcase(os.path.realpath(left))==os.path.normcase(os.path.realpath(right))


def validate_chain(*,expected_pid,registered_at,now,child,parent,registered,python_image,launcher_image):
    if (type(expected_pid) is not int or expected_pid<=0 or expected_pid==child['pid']
            or not isinstance(registered_at,(int,float)) or not math.isfinite(registered_at)
            or registered_at>now or registered['pid']!=expected_pid
            or child['parent_pid']!=parent['pid']
            or any(row['alive'] is not True for row in (child,parent,registered))
            or not registered['created_at']<=registered_at
            or not registered['created_at']<=parent['created_at']<=child['created_at']
            or not same_image(registered['image'],python_image) or not same_image(child['image'],python_image)):
        raise ValueError('Registered parent identity is stale or inconsistent')
    if parent['pid']==expected_pid:
        if parent!=registered:raise ValueError('Direct parent identity changed')
        route='direct'
    elif (parent['parent_pid']==expected_pid and same_image(parent['image'],launcher_image)
            and not same_image(launcher_image,python_image)):
        route='windows_venv_launcher'
    else:
        raise ValueError('Worker is not a child of its registered parent or qualified venv launcher')
    return dict(route=route,pid=child['pid'],parent_pid=parent['pid'],registered_parent_pid=expected_pid,
        child=child,parent=parent,registered=registered)


def kernel_api():
    if os.name!='nt':raise OSError('Windows process identity inspection required')
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    signatures={
        'OpenProcess':([wintypes.DWORD,wintypes.BOOL,wintypes.DWORD],wintypes.HANDLE),
        'CloseHandle':([wintypes.HANDLE],wintypes.BOOL),
        'WaitForSingleObject':([wintypes.HANDLE,wintypes.DWORD],wintypes.DWORD),
        'QueryFullProcessImageNameW':([wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)],wintypes.BOOL),
        'GetProcessTimes':([wintypes.HANDLE]+[ctypes.POINTER(wintypes.FILETIME)]*4,wintypes.BOOL),
        'CreateToolhelp32Snapshot':([wintypes.DWORD,wintypes.DWORD],wintypes.HANDLE),
    }
    for name,(args,result) in signatures.items():
        fn=getattr(api,name);fn.argtypes=args;fn.restype=result
    return api


def snapshot_parent(api,pid):
    class Entry(ctypes.Structure):
        _fields_=[('dwSize',wintypes.DWORD),('cntUsage',wintypes.DWORD),('pid',wintypes.DWORD),
            ('heap',ctypes.c_size_t),('module',wintypes.DWORD),('threads',wintypes.DWORD),
            ('parent_pid',wintypes.DWORD),('priority',wintypes.LONG),('flags',wintypes.DWORD),
            ('exe',wintypes.WCHAR*260)]
    for name in ('Process32FirstW','Process32NextW'):
        fn=getattr(api,name);fn.argtypes=[wintypes.HANDLE,ctypes.POINTER(Entry)];fn.restype=wintypes.BOOL
    handle=api.CreateToolhelp32Snapshot(2,0)
    if handle==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
    try:
        entry=Entry();entry.dwSize=ctypes.sizeof(entry)
        more=api.Process32FirstW(handle,ctypes.byref(entry))
        while more:
            if entry.pid==pid:return entry.parent_pid
            more=api.Process32NextW(handle,ctypes.byref(entry))
        raise ValueError('Process absent from live parent snapshot')
    finally:api.CloseHandle(handle)


@contextmanager
def windows_process(pid):
    """Keep the process handle alive across the complete relationship check."""
    api=kernel_api();handle=api.OpenProcess(0x1000|0x100000,False,pid)
    if not handle:raise ctypes.WinError(ctypes.get_last_error())
    try:
        buffer=ctypes.create_unicode_buffer(32768);size=wintypes.DWORD(len(buffer))
        if not api.QueryFullProcessImageNameW(handle,0,buffer,ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        times=[wintypes.FILETIME() for _ in range(4)]
        if not api.GetProcessTimes(handle,*(ctypes.byref(t) for t in times)):
            raise ctypes.WinError(ctypes.get_last_error())
        ticks=(times[0].dwHighDateTime<<32)|times[0].dwLowDateTime
        yield dict(pid=pid,parent_pid=snapshot_parent(api,pid),image=buffer.value,
            created_at=(ticks-116444736000000000)/10000000,alive=api.WaitForSingleObject(handle,0)==0x102)
        if api.WaitForSingleObject(handle,0)!=0x102:raise ValueError('Parent exited during identity verification')
    finally:api.CloseHandle(handle)


def require_registered_parent(expected_pid,registered_at):
    if type(expected_pid) is not int or expected_pid<=0:raise ValueError('Invalid registered parent PID')
    with ExitStack() as stack:
        child=stack.enter_context(windows_process(os.getpid()))
        parent=stack.enter_context(windows_process(os.getppid()))
        registered=parent if parent['pid']==expected_pid else stack.enter_context(windows_process(expected_pid))
        return validate_chain(expected_pid=expected_pid,registered_at=registered_at,now=time.time(),
            child=child,parent=parent,registered=registered,python_image=sys._base_executable,launcher_image=sys.executable)
