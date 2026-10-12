import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import reader_supervision as R


class ReaderSupervisionTests(unittest.TestCase):
    def execute(self, code, folder, **kwargs):
        return R.run_reader([sys.executable, '-u', '-c', code], Path.cwd(), folder, **kwargs)

    def test_success_preserves_streams_and_exit(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'reader'
            result=self.execute("import sys; print('complete'); print('detail',file=sys.stderr)", p)
            self.assertEqual(result['stdout'].strip(), 'complete')
            self.assertEqual(result['stderr'].strip(), 'detail')
            self.assertTrue(json.loads((p/'exit.json').read_text())['process_stopped'])

    def test_failed_exit_preserves_error_and_cannot_pass(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'reader'
            with self.assertRaises(R.ReaderFailure):
                self.execute("import sys; print('bad',file=sys.stderr); sys.exit(7)", p)
            record=json.loads((p/'exit.json').read_text())
            self.assertEqual(record['returncode'],7)
            self.assertEqual((p/'stderr.txt').read_text().strip(),'bad')

    def test_timeout_stops_child_and_records_it(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'reader'
            with self.assertRaises(R.ReaderFailure):
                self.execute('import time; time.sleep(10)',p,timeout_s=.25)
            record=json.loads((p/'exit.json').read_text())
            self.assertEqual(record['status'],'timeout')
            self.assertTrue(record['process_stopped'])
            self.assertIsInstance(record['pid'],int)

    def test_parent_guard_failure_stops_child(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'reader'
            calls=[]
            def guard():
                calls.append(1)
                if len(calls)>1:raise RuntimeError('parent stopped')
            with self.assertRaises(R.ReaderFailure):
                self.execute('import time; time.sleep(10)',p,guard=guard)
            record=json.loads((p/'exit.json').read_text())
            self.assertEqual(record['status'],'supervision_error')
            self.assertTrue(record['process_stopped'])


if __name__=='__main__':unittest.main()
