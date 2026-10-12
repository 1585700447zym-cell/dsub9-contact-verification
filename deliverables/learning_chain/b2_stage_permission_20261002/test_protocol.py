import copy
import tempfile
import unittest
from pathlib import Path
import paired_contract as C

class Protocol(unittest.TestCase):
    def test_exact_paired_order_and_budget(self):
        a=C.attempts()
        self.assertEqual(len(a),30)
        self.assertEqual([x['arm'] for x in a[4:12]],['F','S']*4)
        self.assertEqual([x['arm'] for x in a[12:20]],['F','S']*4)
        self.assertEqual([x['arm'] for x in a[20:28]],['F','S']*4)
        self.assertEqual([x['stage'] for x in a[28:]],['restore']*2)
        self.assertEqual(C.scope()['training_batches_cap'],5000)
        self.assertEqual(C.scope()['cumulative_dynamic_cap'],120)

    def ledger(self,folder):return C.Ledger.create(Path(folder)/'ledger.json','a'*64,'b'*64)
    def row(self,i,guard=False,success=False):
        return dict(**C.attempts()[i],completed=True,cycles=100,simulation_valid=True,
                    physical_stopped=True,guard_hit=guard,success=success,training_batches=0)

    def test_ordinary_baseline_failure_continues(self):
        with tempfile.TemporaryDirectory() as d:
            l=self.ledger(d)
            for i in range(4):l.start(C.attempts()[i]['id']);l.finish(self.row(i))
            self.assertEqual(l.state['status'],'healthy')
            l.start(C.attempts()[4]['id'])
            self.assertEqual(l.accounting()['new_dynamic_starts'],5)

    def test_guard_closes_all_credit(self):
        with tempfile.TemporaryDirectory() as d:
            l=self.ledger(d);l.start(C.attempts()[0]['id']);l.finish(self.row(0,guard=True))
            with self.assertRaises(RuntimeError):l.start(C.attempts()[1]['id'])
            with self.assertRaises(RuntimeError):l.reserve_update('F')
            self.assertEqual(l.state['status'],'stopped')

    def test_no_unearned_update_or_out_of_order_start(self):
        with tempfile.TemporaryDirectory() as d:
            l=self.ledger(d)
            with self.assertRaises(RuntimeError):l.reserve_update('F')
            with self.assertRaises(RuntimeError):l.start(C.attempts()[1]['id'])

    def test_modes_only_differ_in_permission_and_identity(self):
        f,s=C.config('F'),C.config('S')
        self.assertEqual(f['action']['scale'],[.00005,.00005,.0005,.0005])
        self.assertEqual(s['action']['scale'],f['action']['scale'])
        self.assertEqual(f['stage_permission']['phases'],['INSERT','SEARCH'])
        self.assertEqual(s['stage_permission']['phases'],['SEARCH'])
        f.pop('stage_permission');s.pop('stage_permission');f.pop('comparison');s.pop('comparison')
        self.assertEqual(f,s)

    def test_write_failure_does_not_grant_lease(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            l=self.ledger(d)
            with patch.object(C,'write',side_effect=OSError('disk')):
                with self.assertRaises(OSError):l.start(C.attempts()[0]['id'])
            self.assertTrue(l.write_failed)
            with self.assertRaises(RuntimeError):l.start(C.attempts()[0]['id'])

if __name__=='__main__':unittest.main()
