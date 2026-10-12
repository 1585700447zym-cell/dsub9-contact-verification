import importlib.util,json,sys,tempfile,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))

class NightProtocol(unittest.TestCase):
    def setUp(self):
        import night_contract as N
        self.N=N;self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'ledger.json'
    def ledger(self,variant='base'):return self.N.Ledger.create(self.path,'a'*64,'b'*64,variant)
    def row(self,guard=False,success=True):
        return dict(completed=True,success=success,simulation_valid=True,physical_stopped=True,guard_hit=guard,cycles=12,actor_states=12,physical_substeps=120)
    def test_scope_and_small_scale(self):
        s=self.N.scope();self.assertEqual(s['dynamic_cap'],10);self.assertEqual(s['training_batches'],0)
        base=self.N.config('base');small=self.N.config('small');self.assertEqual(base['action']['scale'][:2],[.00015,.00015]);self.assertEqual(small['action']['scale'],[.00005,.00005,.0005,.0005])
        base['action']['scale']=small['action']['scale'];self.assertEqual(base,small)
    def test_order_and_no_duplicate(self):
        l=self.ledger()
        with self.assertRaises(RuntimeError):l.start(1)
        l.start(0)
        with self.assertRaises(RuntimeError):l.start(0)
        l.finish(self.row());l.start(1);self.assertEqual(l.accounting()['new_dynamic_starts'],2)
    def test_guard_closes_candidate(self):
        l=self.ledger();l.start(0);l.finish(self.row(True,False))
        with self.assertRaises(RuntimeError):l.start(1)
        self.assertEqual(l.state['status'],'stopped')
    def test_ordinary_failure_continues(self):
        l=self.ledger();l.start(0);l.finish(self.row(False,False));l.start(1)
        self.assertEqual(l.state['status'],'healthy')
    def test_fault_retains_started_cost(self):
        l=self.ledger();l.start(0);l.fail('broken');self.assertEqual(l.accounting()['new_dynamic_starts'],1)
        self.assertEqual(l.state['attempts'][0]['status'],'failed')
        with self.assertRaises(RuntimeError):l.start(1)
    def test_no_early_restore(self):
        l=self.ledger()
        with self.assertRaises(RuntimeError):l.start(4)
    def test_restore_only_after_four_and_fifth_cap(self):
        l=self.ledger()
        for i in range(4):l.start(i);l.finish(self.row())
        l.start(4);r=self.row();r.update(restoration_equal=True,source_worker_pid=1,restore_worker_pid=2);l.finish(r);l.complete()
        with self.assertRaises(RuntimeError):l.start(5)
        self.assertEqual(l.accounting()['unused_dynamic'],0)
    def test_tampered_ledger_rejected(self):
        l=self.ledger();d=json.loads(self.path.read_text());d['active']=0;self.path.write_text(json.dumps(d))
        with self.assertRaises((ValueError,RuntimeError)):l.start(0)
    def test_invalid_stop_not_guard_success(self):
        l=self.ledger();l.start(0);r=self.row(True,True)
        with self.assertRaises(ValueError):l.finish(r)
        r=self.row(False,False);r['physical_stopped']=False;l.finish(r);self.assertEqual(l.state['status'],'failed')
    def test_conditional_small_gate(self):
        for status,failures,restore,allowed in [('complete',0,True,False),('complete',1,True,True),('stopped',1,False,True),('failed',1,False,False),('mismatch',1,False,False)]:
            self.assertEqual(self.N.small_allowed(dict(status=status,ordinary_or_guard_failures=failures,restore_ok=restore,operational_fault=False)),allowed)
        self.assertFalse(self.N.small_allowed(dict(status='stopped',ordinary_or_guard_failures=1,operational_fault=True)))
    def test_result_cycle_substep_consistency(self):
        l=self.ledger();l.start(0);r=self.row();r['physical_substeps']=119
        with self.assertRaises(ValueError):l.finish(r)
    def test_mutated_scope_refused(self):
        l=self.ledger();d=json.loads(self.path.read_text());d['scope']['training_batches']=1;self.path.write_text(json.dumps(d))
        with self.assertRaises(ValueError):self.N.Ledger.load(self.path,'a'*64,'b'*64,'base')

class ReviewRegressions(unittest.TestCase):
    def test_five_actual_collector_constructors_have_exclusive_directories(self):
        from run_evaluation import collector_type,collector_output
        from tools.learning.bounded_contact import BoundedAdmission
        with tempfile.TemporaryDirectory() as t:
            permit=object.__new__(BoundedAdmission)
            for i in range(5):
                collector_type()(admission=permit,output=collector_output(Path(t),i),updater=object(),method='sac',checkpoint_sha256='c'*64)
    def test_small_nonzero_action_publishes_through_actual_collector(self):
        import gzip
        from types import SimpleNamespace
        import night_contract as N
        from run_evaluation import collector_type,select_runtime
        select_runtime()
        from tools.learning.bounded_contact import BoundedAdmission
        from tools.learning.episode_rules import FORCE_ONLY
        raw=json.loads(gzip.decompress((N.ROOT/'deliverables/learning_chain/b2_fixed_rotation_cycle_20260928/run/training_episodes/train_04/episode.json.gz').read_bytes()))
        raw.update(fault=None,qualification_sha256='SYNTHETIC-PROTOCOL-ONLY');raw['outcome']['valid_for_learning']=True
        # In-memory mapping fixture only: never represents new physical evidence.
        for row in raw['transitions']:
            a=row['action_log']['raw_action'];requested=[a[0]*.00005,a[1]*.00005,0.,a[2]*.0005,a[3]*.0005,0.]
            row['action_log']['requested_residual']=requested
            row['action_log']['applied_residual']=requested if row['action_active'] else [0.]*6
        self.assertTrue(any(r['action_active'] and abs(r['action_log']['raw_action'][0])>.01 for r in raw['transitions']))
        class Permit(BoundedAdmission):
            episode_rules=FORCE_ONLY
            @property
            def config(self):return N.config('small')
            def verify(self,case=None):return {}
        permit=object.__new__(Permit);u=SimpleNamespace(counts={'critic':2000},fingerprints=lambda:{'actor':N.ACTOR_PIN})
        with tempfile.TemporaryDirectory() as t:
            c=collector_type()(admission=permit,output=Path(t)/'collector',updater=u,method='sac',checkpoint_sha256=N.CHECKPOINT_PIN)
            c._folder=c.output/'synthetic';c._folder.mkdir();c._pending=raw;c._record={'episode_id':raw['episode_id']};c._start_count=dict(u.counts);c._policy_sha=N.ACTOR_PIN
            c.retry_publication()
            self.assertFalse(c._blocked);self.assertEqual(c._record['committed'],0);self.assertEqual(len(c.replay),0)
            self.assertTrue((c._folder/'episode.json.gz').exists())
    def test_confirmed_dead_worker_finalizes_reserved_attempt_without_refund(self):
        import night_contract as N
        with tempfile.TemporaryDirectory() as t:
            f=Path(t);l=N.Ledger.create(f/'ledger.json','a'*64,'b'*64,'base');l.start(0);before=l.path.read_bytes()
            (f/'process').mkdir();N.write(f/'process/started.json',{'supervisor_pid':1});N.write(f/'process/process_exit.json',{'status':'failed','returncode':7})
            N.finalize_failed_exit(f,'a'*64,'b'*64,'base','native exit')
            done=N.Ledger.load(l.path,'a'*64,'b'*64,'base')
            self.assertEqual(done.state['status'],'failed');self.assertIsNone(done.state['active']);self.assertEqual(done.accounting()['new_dynamic_starts'],1)
            self.assertEqual((f/'ledger_before_exit.json').read_bytes(),before)
    def test_unconfirmed_worker_cannot_finalize_or_refund(self):
        import night_contract as N
        with tempfile.TemporaryDirectory() as t:
            f=Path(t);l=N.Ledger.create(f/'ledger.json','a'*64,'b'*64,'base');l.start(0);before=l.path.read_bytes()
            (f/'process').mkdir();N.write(f/'process/started.json',{'supervisor_pid':1})
            with self.assertRaises(RuntimeError):N.finalize_failed_exit(f,'a'*64,'b'*64,'base','uncertain')
            self.assertEqual(l.path.read_bytes(),before)
    def test_report_refuses_started_candidate_missing_assessment(self):
        import night_contract as N
        from report_result import load_assessments
        with tempfile.TemporaryDirectory() as t:
            f=Path(t);(f/'base').mkdir();N.write(f/'base/assessment.json',{'variant':'base'});N.write(f/'small_claim.json',{'pid':2})
            with self.assertRaises(ValueError):load_assessments(f)

class FrozenRunnerProtocol(unittest.TestCase):
    def test_real_permit_constructs_with_registered_deployment_config(self):
        import night_contract as N
        from run_evaluation import permit_type
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as t:
            l=N.Ledger.create(Path(t)/'ledger.json','a'*64,'b'*64,'small');l.start(0)
            with patch.object(N,'verify',return_value={}):
                permit=permit_type()(l,'a'*64,'b'*64)
                self.assertEqual(permit.config['action']['scale'],[.00005,.00005,.0005,.0005])
                self.assertTrue(permit.verify(N.identities()[0])['evaluation_admitted'])
    @unittest.skipUnless(sys.platform=='win32','Actual Windows launcher supervision')
    def test_real_windows_supervisor_guard_and_existing_parent_folder(self):
        import night_contract as N
        from run_evaluation import supervise
        with tempfile.TemporaryDirectory(dir=HERE) as t:
            root=Path(t);process=root/'process'
            child=root/'child.py'
            child.write_text('import sys\nfrom pathlib import Path\nsys.path.insert(0,sys.argv[1])\nfrom run_evaluation import live_guard\nlive_guard(Path(sys.argv[2]))()\nPath(sys.argv[2]).parent.mkdir(exist_ok=True)\nprint("registered worker and existing phase folder verified")\n',encoding='utf-8')
            code=supervise([sys.executable,'-X','utf8','-B',str(child),str(HERE),str(process)],process)
            self.assertEqual(code,0)
            self.assertEqual(N.read(process/'process_exit.json')['returncode'],0)
    @unittest.skipUnless(sys.platform=='win32','Actual Windows stop fence')
    def test_real_windows_fence_rejects_child(self):
        from run_evaluation import supervise
        with tempfile.TemporaryDirectory(dir=HERE) as t:
            root=Path(t);process=root/'process';process.mkdir();(process/'stop_requested.json').write_text('{}')
            child=root/'child.py';child.write_text('import sys\nfrom pathlib import Path\nsys.path.insert(0,sys.argv[1])\nfrom run_evaluation import live_guard\nlive_guard(Path(sys.argv[2]))()\n',encoding='utf-8')
            code=supervise([sys.executable,'-X','utf8','-B',str(child),str(HERE),str(process)],process)
            self.assertNotEqual(code,0)
    def test_meter_refuses_wrong_mode_and_unreserved_state(self):
        import night_contract as N
        from run_evaluation import Meter
        with tempfile.TemporaryDirectory() as t:
            l=N.Ledger.create(Path(t)/'ledger.json','a'*64,'b'*64,'base');m=Meter(l)
            with self.assertRaises(ValueError):m.predict(lambda *a,**k:None,[0.]*120,True)
            l.start(0)
            with self.assertRaises(ValueError):m.predict(lambda *a,**k:None,[0.]*120,False)
            self.assertEqual(m.states,0)
            m.predict(lambda *a,**k:([0.]*4,None),[0.]*120,True);self.assertEqual(m.states,1)
            self.assertFalse(m.in_predict)
    def test_meter_calls_capped_and_exclusive_context(self):
        from run_evaluation import Meter
        class L:
            state=dict(status='healthy',active=0)
            def check_live(self):pass
        m=Meter(L())
        with self.assertRaises(RuntimeError):m.module(lambda:None)
        m.in_predict=True
        for _ in range(32):m.module(lambda:None)
        with self.assertRaises(RuntimeError):m.module(lambda:None)
        m.in_predict=False;m.episode_states=13000
        with self.assertRaises(ValueError):m.predict(lambda *a,**k:None,[0.]*120,True)
    def test_missing_real_restoration_proof_rejected(self):
        import night_contract as N
        self.assertFalse(N.restoration_valid(dict(restoration_equal=True,source_worker_pid=2,restore_worker_pid=2)))
        self.assertFalse(N.restoration_valid(dict(restoration_equal=False,source_worker_pid=2,restore_worker_pid=3)))
        self.assertTrue(N.restoration_valid(dict(restoration_equal=True,source_worker_pid=2,restore_worker_pid=3)))
    def test_forbidden_computation(self):
        from run_evaluation import forbidden
        with self.assertRaises(RuntimeError):forbidden('optimizer')()


if __name__=='__main__':unittest.main()
