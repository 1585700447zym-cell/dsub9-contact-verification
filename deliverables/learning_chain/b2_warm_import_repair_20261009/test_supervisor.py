import json
from pathlib import Path
import sys
import time
import unittest
import uuid
from unittest.mock import patch
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
from supervised import bounded_process
from joint_contract import read,write

class ProcessTests(unittest.TestCase):
    def run_child(self,mode,timeout=5):
        folder=HERE/'test_work'/uuid.uuid4().hex;folder.mkdir(parents=True)
        self.folder=folder;self.start=time.monotonic()
        return bounded_process([sys.executable,'-I','-X','utf8','-B',str(HERE/'fixture_worker.py'),mode,str(folder)],
            folder/'control',timeout,phase_file=folder/'phase.json')

    def assert_closed(self):
        receipt=read(self.folder/'control.supervisor.json')
        self.assertTrue(receipt['process_exit_confirmed']);self.assertTrue(receipt['owned_launcher_exit_confirmed'])
        return receipt

    def test_unknown_phase_stops_instead_of_allowing_child_success(self):
        with self.assertRaises(ValueError):self.run_child('invalid')
        self.assert_closed()

    def test_future_phase_cannot_grant_extra_time(self):
        with self.assertRaises(ValueError):self.run_child('future')
        self.assert_closed()

    def test_normal_child_exits_with_success_receipt(self):
        result=self.run_child('normal');self.assertEqual(result['returncode'],0);self.assert_closed()

    def test_child_error_stops_and_records_owned_exit(self):
        with self.assertRaises(RuntimeError):self.run_child('fail')
        self.assert_closed()

    def test_whole_deadline_stops_descendant_tree(self):
        with self.assertRaises(TimeoutError):self.run_child('hang',timeout=1.5)
        self.assertTrue(self.assert_closed()['deadline_hit']);self.assertLess(time.monotonic()-self.start,4)

    def test_expired_phase_stops_child(self):
        with self.assertRaises(TimeoutError):self.run_child('expired')
        self.assertTrue(self.assert_closed()['deadline_hit'])

    def test_permanent_phase_lock_fails_closed(self):
        with self.assertRaises(TimeoutError):self.run_child('locked')
        self.assert_closed();self.assertLess(time.monotonic()-self.start,2)

    def test_corrupt_phase_stops_child(self):
        with self.assertRaises(json.JSONDecodeError):self.run_child('malformed')
        self.assert_closed()

    def test_final_phase_is_checked_after_fast_child_exit(self):
        sleep=time.sleep
        # Force the real child to exit within one parent poll interval.
        with patch('supervised.time.sleep',side_effect=lambda delay:sleep(max(.1,delay))):
            with self.assertRaises(json.JSONDecodeError):self.run_child('fast_corrupt')
        self.assert_closed()

class PhaseTests(unittest.TestCase):
    def setUp(self):
        from phase_deadline import PhaseDeadline
        self.monitor=PhaseDeadline(time.monotonic()+5)
        self.folder=HERE/'test_work'/uuid.uuid4().hex;self.folder.mkdir(parents=True)
        self.path=self.folder/'phase.json'

    def phase(self,remaining=.08):
        return dict(kind='physical',id='p1',started=time.time()-1200+remaining,limit_s=1200)

    def test_repeated_reads_and_backward_clock_do_not_extend_deadline(self):
        write(self.path,self.phase(.4));self.monitor.read_phase(self.path);end=self.monitor.deadline
        with patch('phase_deadline.time.time',return_value=time.time()-1000):self.monitor.read_phase(self.path)
        self.assertEqual(self.monitor.deadline,end)

    def test_new_record_does_not_rescue_expired_old_phase(self):
        write(self.path,self.phase(.04));self.monitor.read_phase(self.path)
        write(self.path,dict(kind='between_episodes',started=time.time(),limit_s=1800))
        time.sleep(.05)
        with self.assertRaises(TimeoutError):self.monitor.read_phase(self.path)

    def test_locked_read_respects_last_phase_deadline(self):
        from test_io_repair import exclusive
        write(self.path,self.phase(.07));self.monitor.read_phase(self.path)
        release=exclusive(self.path);start=time.monotonic()
        try:
            with self.assertRaises(TimeoutError):self.monitor.read_phase(self.path)
        finally:release()
        self.assertLess(time.monotonic()-start,.25)

    def test_missing_file_is_allowed_only_before_first_phase(self):
        self.assertIsNone(self.monitor.read_phase(self.path))
        write(self.path,self.phase(.4));self.monitor.read_phase(self.path)
        with self.assertRaises(FileNotFoundError):self.monitor.read_phase(self.folder/'missing.json')

    def test_invalid_metadata_rejected(self):
        for change in ({'started':True},{'started':-1},{'limit_s':True},{'limit_s':1800},{'id':''},{'kind':'other'}):
            write(self.path,self.phase(.4)|change)
            with self.assertRaises(ValueError):self.monitor.read_phase(self.path)

    def test_overflow_json_number_rejected(self):
        self.path.write_text('{"started":1e999,"limit_s":1200,"kind":"physical","id":"p1"}',encoding='utf8')
        with self.assertRaises(ValueError):self.monitor.read_phase(self.path)

    def test_first_null_phase_is_invalid(self):
        write(self.path,None)
        with self.assertRaises(ValueError):self.monitor.read_phase(self.path)

    def test_equal_value_with_invalid_type_does_not_bypass_validation(self):
        phase=self.phase(.4);write(self.path,phase);self.monitor.read_phase(self.path)
        phase['limit_s']=1200.0;write(self.path,phase)
        with self.assertRaises(ValueError):self.monitor.read_phase(self.path)

if __name__=='__main__':unittest.main(verbosity=2)
