import copy,importlib,json,tempfile,unittest
from pathlib import Path
try:C=importlib.import_module('validation_contract')
except ModuleNotFoundError as e:
    if e.name!='validation_contract':raise
    C=None

try:R=importlib.import_module('learning_runtime');V=importlib.import_module('run_validation')
except ModuleNotFoundError as e:
    if e.name not in ('learning_runtime','run_validation'):raise
    R=V=None

class RuntimeTests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(R,'Missing current learning runtime');self.assertIsNotNone(V,'Missing supervised validation runner')
    def test_historical_permission_preserved(self):
        raw=dict(training_admitted=False,optimizer_steps=0,optimizer_steps_start=0,fault=None,outcome=dict(valid_for_learning=True,simulation_valid=True,physical_stopped=True))
        receipt=dict(training_admitted=False,committed=0,status='preflight_archived')
        before=copy.deepcopy((raw,receipt));R.source_permission(raw,receipt);self.assertEqual((raw,receipt),before)
    def test_previously_published_rejected(self):
        with self.assertRaises(ValueError):R.source_permission(dict(training_admitted=True),dict(committed=1))
    def test_invalid_source_rejected(self):
        with self.assertRaises(ValueError):R.source_permission(dict(training_admitted=False,optimizer_steps=0,optimizer_steps_start=0,fault=None,outcome=dict(valid_for_learning=False,simulation_valid=True,physical_stopped=True)),dict(training_admitted=False,committed=0,status='preflight_archived'))
    def test_counts_and_history_must_agree(self):
        good=dict(critic=1,target=1,actor=1,temperature=1);R.validate_counts(good,[dict(active_rows=8,critic_batches=1,batch_rows=256)],1)
        with self.assertRaises(ValueError):R.validate_counts(good,[dict(active_rows=0,critic_batches=1,batch_rows=256)],1)
        with self.assertRaises(ValueError):R.validate_counts(good,[],1)
    def test_cross_arm_snapshot_rejected(self):
        with self.assertRaises(ValueError):R.check_snapshot_identity(dict(version='temporal_learning_checkpoint_v1',arm='A',binding_sha256='a'*64,authorization_sha256='b'*64,config=C.config('A')),'C','a'*64,'b'*64)
    def test_authorization_precedes_runtime(self):
        from unittest.mock import patch
        order=[]
        with patch.object(V,'require_authorization',side_effect=lambda *a:order.append('authorization') or (_ for _ in ()).throw(ValueError('absent'))),patch.object(V,'select_runtime',side_effect=lambda:order.append('runtime')):
            with self.assertRaises(ValueError):V.entry_checks('a'*64,'b'*64)
        self.assertEqual(order,['authorization'])
    def test_physics_unreserved_refused(self):
        from types import SimpleNamespace
        ledger=SimpleNamespace(state=dict(status='healthy',active=None),write_failed=False,check_live=lambda:None)
        meter=V.PhysicsBudget(ledger)
        with self.assertRaises(RuntimeError):meter.step(lambda *a,**k:None,1,2)
        self.assertEqual(meter.total_substeps,0)
    def test_physics_failure_is_charged(self):
        from types import SimpleNamespace
        ledger=SimpleNamespace(state=dict(status='healthy',active=0),write_failed=False,check_live=lambda:None)
        meter=V.PhysicsBudget(ledger);meter.begin()
        def fail(*a):raise RuntimeError('physical failure')
        with self.assertRaises(RuntimeError):meter.step(fail,1,2)
        self.assertEqual(meter.total_substeps,1)
    def test_model_and_optimizer_without_lease_refused(self):
        from types import SimpleNamespace
        ledger=SimpleNamespace(state=dict(status='healthy',active=None,update_lease=None),write_failed=False)
        meter=V.LearningMeter(ledger)
        with self.assertRaises(RuntimeError):meter.module(lambda:None)
        with self.assertRaises(RuntimeError):meter.optimizer(lambda:None)
        self.assertEqual((meter.module_calls,meter.optimizer_calls),(0,0))
    def test_stopped_ledger_refuses_model(self):
        from types import SimpleNamespace
        ledger=SimpleNamespace(state=dict(status='stopped',active=0,update_lease=None),write_failed=False)
        meter=V.LearningMeter(ledger)
        with self.assertRaises(RuntimeError):meter.begin_control()
    def test_complete_preflight_requalification_is_separate(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as tmp:
            ledger=SimpleNamespace(state=dict(binding_sha256='a'*64,authorization_sha256='b'*64),register_dataset=lambda *a:None)
            before={p:C.digest(p) for p in (C.PREFLIGHT/'run/episodes').glob('*/*') if p.is_file()}
            with patch.object(C,'require_authorization'),patch.object(C,'verify_parent'):
                m,pin=R.qualify_dataset('C',ledger,Path(tmp))
            self.assertEqual(len(m['references']),4);self.assertTrue(all(r['training_admitted'] and not r['historical_training_admitted'] for r in m['current_receipts']))
            self.assertEqual(before,{p:C.digest(p) for p in before})
    def test_module_failure_charge_and_local_cap(self):
        from types import SimpleNamespace
        ledger=SimpleNamespace(state=dict(status='healthy',active=0,update_lease=None),write_failed=False)
        meter=V.LearningMeter(ledger);meter.begin_control()
        def fail():raise RuntimeError('call failed')
        with self.assertRaises(RuntimeError):meter.module(fail)
        for _ in range(31):meter.module(lambda:None)
        with self.assertRaises(RuntimeError):meter.module(lambda:None)
        self.assertEqual(meter.module_calls,32)
    def test_new_meter_reuses_live_checked_fault_tail(self):
        from run_preflight import collector_type as old_type
        self.assertIs(V.collector_type()._stop_tail.__code__,old_type()._stop_tail.__code__)
    def test_dataset_digest_preserves_windows_line_endings(self):
        import hashlib
        m=dict(version='temporal_dataset_qualification_v1',arm='C');data=json.dumps(m,indent=2).replace('\n','\r\n').encode()
        pin=hashlib.sha256(data).hexdigest();R.verify_dataset_bytes(m,data,pin)
        with self.assertRaises(ValueError):R.verify_dataset_bytes(m,data.replace(b'\r\n',b'\n'),pin)
    def test_confirmed_worker_death_closes_attempted_lease(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'run').mkdir();l=C.Ledger.create(root/'run/ledger.json','a'*64,'b'*64)
            for i in range(4):l.start(C.attempts()[i]['id']);l.finish(dict(**C.attempts()[i],completed=True,cycles=10,success=True,simulation_valid=True,physical_stopped=True,guard_hit=False))
            l.register_dataset('C','c'*64,['c0','c1','c2','c3']);l.reserve_update('C');C.write(root/'process_exit.json',dict(status='failed',returncode=-9))
            with patch.object(V,'HERE',root):V.finalize_exception('a'*64,'b'*64,RuntimeError('native crash'))
            s=C.read(root/'run/ledger.json');self.assertEqual(s['status'],'failed');self.assertIsNone(s['update_lease']);self.assertEqual(s['updates']['C']['attempted'],1)
    def test_uncertain_cleanup_preserves_active_reservation(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'run').mkdir();l=C.Ledger.create(root/'run/ledger.json','a'*64,'b'*64);l.start(C.attempts()[0]['id']);before=copy.deepcopy(l.state)
            C.write(root/'process_exit.json',dict(status='supervisor_error',worker_stopped=False,cleanup_error='unknown'))
            with patch.object(V,'HERE',root):V.finalize_exception('a'*64,'b'*64,RuntimeError('lost worker'))
            self.assertEqual(C.read(root/'run/ledger.json'),before);self.assertTrue((root/'stop_requested.json').exists())
    def test_checkpoint_boundary_before_next_online(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        branch=SimpleNamespace(arm='C',history=[{}]*500,save=lambda p:seen.append(str(p)) or 'c'*64);seen=[]
        with tempfile.TemporaryDirectory() as tmp:
            result=V.save_boundary(branch,Path(tmp))
            self.assertEqual(result['batches'],500);self.assertTrue(seen[0].endswith('checkpoint_C_0500'))
    def test_latched_guard_tail_does_not_run_model(self):
        from types import SimpleNamespace
        import numpy as np
        snap=SimpleNamespace(policy_observation=[0.]*120)
        def forbidden(*a,**k):raise AssertionError('Guard tail ran model')
        collector=SimpleNamespace(session=SimpleNamespace(cycle_id=1,prepare_cycle=lambda:snap,env=SimpleNamespace(guard_facts=dict(contact_reasons=['FORCE_LIMIT'],motion_reasons=[],invalid_reasons=[]))),
            admission=SimpleNamespace(ledger=SimpleNamespace(check_live=lambda:None)),updater=SimpleNamespace(predict=forbidden))
        meter=SimpleNamespace(begin_control=forbidden,end_context=lambda:None)
        action,_=V.ContextPolicy(collector,meter,False).predict(np.zeros(120,dtype=np.float32),deterministic=False)
        self.assertEqual(action.tolist(),[0.]*4)

class ContractTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(C,'Missing bounded learning-validation contract')
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'ledger.json';self.pin='a'*64;self.auth='b'*64
    def ledger(self):return C.Ledger.create(self.path,self.pin,self.auth)
    def test_forged_guard_history_cannot_resume(self):
        l=self.ledger();l.start(C.attempts()[0]['id']);l.finish(self.row(0,success=False,guard_hit=True))
        s=copy.deepcopy(l.state);s['status']='healthy'
        with self.assertRaises(ValueError):C.Ledger(self.path,s)
    def test_forged_update_lease_rejected(self):
        l=self.ledger();self.initial(l);self.dataset(l);l.reserve_update('C');s=copy.deepcopy(l.state);s['update_lease']['batch']=8
        with self.assertRaises(ValueError):C.Ledger(self.path,s)
    def row(self,i,**kw):
        r=dict(**C.attempts()[i],completed=True,cycles=10,success=True,simulation_valid=True,physical_stopped=True,guard_hit=False)
        r.update(kw);return r
    def initial(self,l):
        for i in range(4):l.start(C.attempts()[i]['id']);l.finish(self.row(i))
    def dataset(self,l,arm='C'):
        l.register_dataset(arm,'c'*64,[arm+str(i) for i in range(4)])
    def updates(self,l,n=500,arm='C'):
        for _ in range(n):token=l.reserve_update(arm);l.finish_update(token)
    def test_exact_scope_and_candidate_first(self):
        s=C.scope();self.assertEqual((s['dynamic_cap'],s['previous_dynamic'],s['cumulative_dynamic_cap'],s['training_batches_cap']),(24,68,92,5000))
        self.assertEqual([x['stage'] for x in C.attempts()],[s for s in ('initial','C_online','C_final','C_restored','A_online','A_final') for _ in range(4)])
    def test_reserve_before_physics_and_no_second_active(self):
        l=self.ledger();l.start(C.attempts()[0]['id']);self.assertEqual(l.accounting()['control_cycles_reserved'],13000)
        with self.assertRaises(RuntimeError):l.start(C.attempts()[1]['id'])
    def test_update_requires_current_dataset_and_initial_pass(self):
        l=self.ledger();self.dataset(l)
        with self.assertRaises(RuntimeError):l.reserve_update('C')
        self.initial(l);token=l.reserve_update('C');self.assertEqual(l.accounting()['formal_batches_attempted'],1)
        self.assertEqual(l.state['updates']['C']['completed'],0)
        with self.assertRaises(RuntimeError):l.reserve_update('C')
        l.finish_update(token)
    def test_credit_500_after_four_and_no_duplicate_credit(self):
        l=self.ledger();self.initial(l);self.dataset(l);self.updates(l)
        with self.assertRaises(RuntimeError):l.reserve_update('C')
        with self.assertRaises(RuntimeError):self.dataset(l)
        l.start(C.attempts()[4]['id']);l.finish(self.row(4));l.reserve_update('C')
    def test_online_requires_exact_preceding_updates(self):
        l=self.ledger();self.initial(l);self.dataset(l)
        with self.assertRaises(RuntimeError):l.start(C.attempts()[4]['id'])
    def test_any_guard_stops_whole_stage(self):
        l=self.ledger();l.start(C.attempts()[0]['id']);l.finish(self.row(0,success=False,guard_hit=True))
        self.assertEqual(l.state['status'],'stopped')
        with self.assertRaises(RuntimeError):l.start(C.attempts()[1]['id'])
        with self.assertRaises(RuntimeError):l.reserve_update('C')
    def test_initial_not_four_successes_closes_after_four(self):
        l=self.ledger()
        for i in range(4):l.start(C.attempts()[i]['id']);l.finish(self.row(i,success=i!=1))
        self.assertEqual(l.state['status'],'baseline_failed')
    def test_wrong_identity_or_impossible_result_rejected(self):
        l=self.ledger();l.start(C.attempts()[0]['id'])
        for r in (self.row(1),self.row(0,cycles=13001),self.row(0,success=True,guard_hit=True)):
            with self.assertRaises(ValueError):l.finish(r)
    def test_inactive_or_stale_update_token_refused(self):
        l=self.ledger();self.initial(l);self.dataset(l);t=l.reserve_update('C');l.finish_update(t)
        with self.assertRaises(RuntimeError):l.finish_update(t)
    def test_stale_ledger_cannot_write(self):
        l=self.ledger();q=C.Ledger.load(self.path,self.pin,self.auth);l.start(C.attempts()[0]['id'])
        with self.assertRaises(RuntimeError):q.start(C.attempts()[0]['id'])
    def test_fault_attempt_not_refunded(self):
        l=self.ledger();self.initial(l);self.dataset(l);l.reserve_update('C');l.fail('fault')
        self.assertEqual(l.accounting()['formal_batches_attempted'],1);self.assertEqual(l.accounting()['formal_batches_completed'],0)
        with self.assertRaises(RuntimeError):l.reserve_update('C')
    def test_new_authorization_scope_not_old_eight_zero(self):
        a=dict(version='temporal_learning_authorization_v1',approved=True,binding_sha256=self.pin,scope=C.scope(),user_confirmation='直接做到验证结束')
        C.validate_authorization(a,self.pin)
        for key,value in [('dynamic_cap',25),('training_batches_cap',0),('stop_on_any_guard',False)]:
            b=copy.deepcopy(a);b['scope'][key]=value
            with self.assertRaises(ValueError):C.validate_authorization(b,self.pin)
    def test_cross_binding_or_auth_restore_refused(self):
        self.ledger()
        with self.assertRaises(ValueError):C.Ledger.load(self.path,'d'*64,self.auth)
    def test_data_id_duplicates_refused(self):
        l=self.ledger()
        with self.assertRaises(ValueError):l.register_dataset('C','c'*64,['x']*4)
    def test_write_fault_poison(self):
        l=self.ledger();original=C.write
        C.write=lambda *a:(_ for _ in ()).throw(OSError('disk'))
        try:
            with self.assertRaises(OSError):l.start(C.attempts()[0]['id'])
        finally:C.write=original
        with self.assertRaises(RuntimeError):l.start(C.attempts()[0]['id'])

if __name__=='__main__':unittest.main()
