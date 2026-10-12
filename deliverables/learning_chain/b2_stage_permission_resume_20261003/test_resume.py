from copy import deepcopy
import importlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent


class ResumeContractTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((HERE/'paired_contract.py').exists(),'Resume contract is not implemented')
        self.C=importlib.import_module('paired_contract')
        self.temp=tempfile.TemporaryDirectory(dir=self.C.ROOT/'tmp');self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'ledger.json'
        self.ledger=self.C.Ledger.create(self.path,'a'*64,'b'*64)

    def proof(self,arm):
        return dict(complete_equal=True,pid=os.getpid()+100+(arm=='S'),manifest_sha256='c'*64,
            calls=dict(model_forward=0,optimizer=0,physics=0),batches=0,arm=arm,
            binding_sha256='a'*64,authorization_sha256='b'*64)

    def admit_data(self):
        for arm in ('F','S'):
            self.ledger.register_dataset(arm,'d'*64,[r['id'] for r in self.ledger.rows('warmup',arm)])
        self.ledger.admit_warmup('e'*64)

    def test_inherited_prefix_costs_zero_new_starts(self):
        a=self.ledger.accounting()
        self.assertEqual((a['new_dynamic_starts'],a['cumulative_dynamic'],a['unused_dynamic']),(0,102,18))
        self.assertEqual((a['control_cycles_reserved'],a['control_cycles_confirmed']),(0,0))
        self.assertEqual(len(self.ledger.rows('warmup')),8)
        self.assertEqual(sum(r['success'] for r in self.ledger.rows('b2')),3)

    def test_cannot_repeat_inherited_collection(self):
        with self.assertRaises(RuntimeError):self.ledger.start('b2_B2_x_pos_100')
        with self.assertRaises(RuntimeError):self.ledger.start('warmup_F_x_pos_100')
        self.assertEqual(self.ledger.accounting()['new_dynamic_starts'],0)

    def test_tampered_inherited_result_rejected(self):
        state=deepcopy(self.ledger.state)
        state['attempts'][0]['result']['success']=False
        with self.assertRaises(ValueError):self.C.Ledger(self.path,state)

    def test_training_requires_both_actual_reader_proofs(self):
        self.admit_data()
        with self.assertRaises(RuntimeError):self.ledger.reserve_update('F')
        self.ledger.register_zero_reader('F','c'*64,self.proof('F'))
        with self.assertRaises(RuntimeError):self.ledger.reserve_update('F')
        self.ledger.register_zero_reader('S','c'*64,self.proof('S'))
        lease=self.ledger.reserve_update('F')
        self.assertEqual(lease['batch'],1)
        self.assertEqual(self.ledger.accounting()['formal_batches_completed'],0)

    def test_reader_with_compute_or_wrong_branch_cannot_admit(self):
        self.admit_data()
        p=self.proof('F');p['calls']['physics']=1
        with self.assertRaises(ValueError):self.ledger.register_zero_reader('F','c'*64,p)
        with self.assertRaises(ValueError):self.ledger.register_zero_reader('S','c'*64,self.proof('F'))

    def test_reader_pid_independence_checked_at_registration_not_later(self):
        self.admit_data()
        own=self.proof('F');own['pid']=os.getpid()
        with self.assertRaises(ValueError):self.ledger.register_zero_reader('F','c'*64,own)
        proof=self.proof('F');self.ledger.register_zero_reader('F','c'*64,proof)
        with patch.object(self.C.os,'getpid',return_value=proof['pid']):
            restored=self.C.Ledger.load(self.path,'a'*64,'b'*64)
        self.assertEqual(restored.state['zero_readers']['F'],proof)

    def test_inherited_binding_only_for_registered_warmup(self):
        self.assertEqual(self.C.source_binding('F','warmup','a'*64),
                         '399367199645decfed696c31e48dee0727117485b3673d028c52a0c5db392a46')
        self.assertEqual(self.C.source_binding('F','online','a'*64),'a'*64)
        with self.assertRaises(ValueError):self.C.source_binding('F','final','a'*64)

    def test_new_dynamic_is_counted_once_and_guard_closes_run(self):
        self.admit_data()
        for arm in ('F','S'):self.ledger.register_zero_reader(arm,'c'*64,self.proof(arm))
        state=deepcopy(self.ledger.state);state['updates']['F']=dict(attempted=500,completed=500)
        self.ledger.commit(state)
        self.ledger.start('online_F_x_pos_100')
        r=dict(self.C.attempts()[12],completed=True,success=False,simulation_valid=True,physical_stopped=True,guard_hit=True,cycles=2)
        self.ledger.finish(r)
        a=self.ledger.accounting()
        self.assertEqual((a['new_dynamic_starts'],a['cumulative_dynamic'],a['control_cycles_confirmed']),(1,103,2))
        with self.assertRaises(RuntimeError):self.ledger.reserve_update('S')

    def test_eighteenth_new_start_exhausts_budget(self):
        self.admit_data()
        for arm in ('F','S'):self.ledger.register_zero_reader(arm,'c'*64,self.proof(arm))
        state=deepcopy(self.ledger.state)
        for identity in self.C.attempts()[12:]:
            r=dict(identity,completed=True,success=False,simulation_valid=True,physical_stopped=True,guard_hit=False,cycles=1)
            state['attempts'].append(dict(identity=identity,status='finished',reserved_cycles=13000,result=r))
        state['updates']={arm:dict(attempted=2500,completed=2500) for arm in ('F','S')}
        self.ledger.commit(state)
        a=self.ledger.accounting()
        self.assertEqual((a['new_dynamic_starts'],a['cumulative_dynamic'],a['unused_dynamic']),(18,120,0))
        self.assertEqual(a['control_cycles_confirmed'],18)
        with self.assertRaises(RuntimeError):self.ledger.start('online_F_x_pos_100')


if __name__=='__main__':unittest.main()
