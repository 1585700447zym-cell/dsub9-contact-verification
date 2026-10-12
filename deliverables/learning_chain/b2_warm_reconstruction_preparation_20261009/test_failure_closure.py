from pathlib import Path
import sys,unittest,uuid
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
from gate_contract import Counter
from joint_contract import read
from supervised import bounded_process
from run_gate import finalize_execution

class ClosureTests(unittest.TestCase):
    def folder(self):
        p=HERE/'test_work'/uuid.uuid4().hex;p.mkdir(parents=True);return p

    def test_timed_out_owned_worker_leaves_lock_and_still_closes(self):
        folder=self.folder();counter=Counter.create(folder/'counter.json')
        with self.assertRaises(TimeoutError):
            bounded_process([sys.executable,'-I','-X','utf8','-B',str(HERE/'fixture_orphan_lock.py'),str(folder)],folder/'supervisor',1.5)
        self.assertTrue((folder/'lock_held.json').exists());self.assertTrue(counter.path.with_suffix('.lock').exists())
        self.assertEqual(finalize_execution(folder,counter,'CLOSED_ERROR'),'CLOSED_ERROR')
        closed=read(folder/'authorization_closure.json')
        self.assertTrue(closed['process_exit_confirmed']);self.assertTrue(closed['counter_closed'])
        self.assertEqual(read(counter.path)['status'],'CLOSED');self.assertFalse(counter.path.with_suffix('.lock').exists())

    def test_unproven_lock_is_preserved_but_failure_receipt_is_durable(self):
        folder=self.folder();counter=Counter.create(folder/'counter.json');lock=counter.path.with_suffix('.lock');lock.write_text('held',encoding='utf8')
        self.assertEqual(finalize_execution(folder,counter,'CLOSED_COMPLETE'),'CLOSED_ERROR')
        self.assertTrue(lock.exists());closed=read(folder/'authorization_closure.json')
        self.assertFalse(closed['counter_closed']);self.assertFalse(closed['process_exit_confirmed'])
        self.assertTrue(closed['unused_closed']);self.assertIn('TimeoutError',closed['counter_error'])

if __name__=='__main__':unittest.main(verbosity=2)
