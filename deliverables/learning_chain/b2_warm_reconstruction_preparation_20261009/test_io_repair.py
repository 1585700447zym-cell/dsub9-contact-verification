"""Real Windows file locking and concurrent readers/writers; no simulation."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sys
import threading
import time
import unittest
import uuid
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from joint_contract import read,write

def exclusive(path):
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    create=kernel.CreateFileW
    create.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
    create.restype=wintypes.HANDLE
    handle=create(str(path),0x80000000,0,None,3,0,None)
    if handle==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
    close=kernel.CloseHandle;close.argtypes=[wintypes.HANDLE];close.restype=wintypes.BOOL
    def release():
        if not close(handle):raise ctypes.WinError(ctypes.get_last_error())
    return release

class IOTests(unittest.TestCase):
    def setUp(self):
        self.folder=HERE/'test_work'/uuid.uuid4().hex;self.folder.mkdir(parents=True)
        self.path=self.folder/'value.json';self.path.write_text('{"n":1}',encoding='utf8')

    def temporary_lock(self,operation):
        release=exclusive(self.path)
        timer=threading.Timer(.08,release);timer.start()
        error=None;result=None
        try:
            try:result=operation()
            except Exception as exc:error=exc
        finally:timer.join()
        self.assertIsNone(error,'Short-lived Windows sharing conflicts must recover: '+repr(error))
        return result

    def test_read_recovers_after_temporary_windows_lock(self):
        self.assertEqual(self.temporary_lock(lambda:read(self.path)),{'n':1})

    def test_replace_recovers_after_temporary_windows_lock(self):
        self.temporary_lock(lambda:write(self.path,{'n':2}))
        self.assertEqual(json.loads(self.path.read_text()),{'n':2})

    def test_persistent_lock_obeys_external_deadline(self):
        release=exclusive(self.path);start=time.monotonic()
        try:
            with self.assertRaises(TimeoutError):read(self.path,deadline=start+.07)
        finally:release()
        self.assertLess(time.monotonic()-start,.3)

    def test_failed_replace_keeps_old_value_and_staged_new_value(self):
        release=exclusive(self.path)
        try:
            with self.assertRaises(TimeoutError):write(self.path,{'n':2},deadline=time.monotonic()+.05)
        finally:release()
        self.assertEqual(read(self.path),{'n':1})
        self.assertEqual([read(p) for p in self.folder.glob('*.tmp-*')],[{'n':2}])

    def test_default_permanent_denial_is_bounded(self):
        release=exclusive(self.path);start=time.monotonic()
        try:
            with self.assertRaises(TimeoutError):read(self.path)
        finally:release()
        self.assertLess(time.monotonic()-start,1.)

    def test_expired_write_does_not_modify_destination(self):
        with self.assertRaises(TimeoutError):write(self.path,{'n':99},deadline=time.monotonic()-1)
        self.assertEqual(read(self.path),{'n':1})

    def test_invalid_json_and_non_permission_errors_fail_immediately(self):
        self.path.write_text('{broken',encoding='utf8')
        with self.assertRaises(json.JSONDecodeError):read(self.path)
        with self.assertRaises(FileNotFoundError):read(self.folder/'missing.json')
        with patch('bounded_io.os.replace',side_effect=OSError(28,'disk full')):
            with self.assertRaises(OSError) as caught:write(self.folder/'new.json',{'n':3})
        self.assertEqual(caught.exception.errno,28)

    def test_nonfinite_or_invalid_deadline_rejected(self):
        for deadline in (float('nan'),float('inf'),True,'later'):
            with self.assertRaises(ValueError):read(self.path,deadline=deadline)

    def test_delayed_success_is_not_accepted_after_deadline(self):
        from bounded_io import retry_io
        def slow():time.sleep(.025);return 7
        with self.assertRaises(TimeoutError):retry_io(slow,deadline=time.monotonic()+.01)

    def test_concurrent_replacement_yields_only_complete_json(self):
        errors=[];stop=threading.Event();count=[0]
        def reader():
            while not stop.is_set():
                try:
                    data=read(self.path)
                    if data['n']!=len(data.get('s','x')):raise AssertionError(data)
                    count[0]+=1
                except Exception as exc:errors.append(repr(exc));stop.set()
        t=threading.Thread(target=reader);t.start()
        try:
            for i in range(1,150):write(self.path,{'n':i,'s':'x'*i})
        finally:stop.set();t.join(2)
        self.assertFalse(t.is_alive());self.assertFalse(errors,errors)
        self.assertGreater(count[0],0);self.assertEqual(read(self.path)['n'],149)

if __name__=='__main__':unittest.main(verbosity=2)
