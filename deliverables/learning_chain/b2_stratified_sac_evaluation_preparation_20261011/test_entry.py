"""Admission and rollout tests with Python fakes; no scientific computation."""
import copy,importlib,math,subprocess,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace as NS
OUT=Path(__file__).resolve().parent;sys.path.insert(0,str(OUT))

class AdmissionTests(unittest.TestCase):
    def setUp(self):self.c=importlib.import_module('sac_scope')
    def row(self,i=0,task='FULL_SUCCESS'):
        item=self.c.schedule()[i]
        return dict(index=i,case_id=item['case_id'],role=item['role'],status='finished',healthy=True,
            initial_audit={'passed':True},archive_sha256='a'*64,
            environment_creation_attempted=1,environment_created=1,reset_attempted=1,reset_completed=1,
            control_cycles=2,physical_substeps=20,policy_calls=1,policy_call_attempts=1,
            actor_construction_attempts=1,actor_constructions=1,tensor_load_attempts=1,tensor_loads=1,
            learner_constructions=0,formal_updates=0,replay_publications=0,
            nonzero_applied_command_cycles=1,max_command_error=0.,
            actor_before=self.c.actor_spec(item['role'])['actor_sha256'],actor_after=self.c.actor_spec(item['role'])['actor_sha256'],
            outcome=dict(simulation_valid=True,physical_stopped=True,guard_violations=dict(contact=False,motion=False),task_outcome=task),
            supervisor=dict(go_issued=True,process_exit_confirmed=True,owned_launcher_exit_confirmed=True,returncode=0))
    def test_schedule(self):
        s=self.c.schedule();self.assertEqual(len(s),42);self.assertEqual(len({(r['case_id'],r['role']) for r in s}),42)
        self.assertEqual([r['case_id'] for r in s[:12:2]],['D00','P4','A1','J12','J23','J14'])
        self.assertEqual({r['phase'] for r in s[:12]},{'dynamic_precheck'})
    def test_grant_draft_refused(self):
        for kind in ('numeric','physical'):
            g=self.c.grant_template(kind,'a'*64,'run-test')
            with self.assertRaises(PermissionError):self.c.require_grant(g,kind,'a'*64,'run-test')
    def test_open_exact_grant(self):
        for kind in ('numeric','physical'):
            g=self.c.grant_template(kind,'a'*64,'run-test');g.update(status='OPEN',explicit_user_authorized=True,human_evidence='new explicit approval')
            self.c.require_grant(g,kind,'a'*64,'run-test')
            for change in [dict(cumulative_before=278),dict(retries=1),dict(run_id='other'),dict(purpose='training')]:
                bad=dict(g,**change)
                with self.assertRaises(PermissionError):self.c.require_grant(bad,kind,'a'*64,'run-test')
            g['limits']['tensor_loads']+=1
            with self.assertRaises(PermissionError):self.c.require_grant(g,kind,'a'*64,'run-test')
    def test_first_12_then_next(self):
        rows=[self.row(i) for i in range(12)];self.assertTrue(self.c.dynamic_precheck(rows)['passed'])
        self.assertEqual(self.c.next_unit(rows),self.c.schedule()[12])
    def test_ordinary_failure_is_scored_and_continues(self):
        r=self.row(task='TASK_FAILURE');self.assertTrue(self.c.receipt_healthy(r))
        self.assertEqual(self.c.next_unit([r]),self.c.schedule()[1])
    def test_invalid_guard_unstopped_close(self):
        for field,value in [('simulation_valid',False),('physical_stopped',False),('task_outcome','CONTACT_GUARD')]:
            r=self.row();r['outcome'][field]=value;self.assertIsNone(self.c.next_unit([r]))
        r=self.row();r['outcome']['guard_violations']['contact']=True;self.assertIsNone(self.c.next_unit([r]))
    def test_exit_or_identity_failure_closes(self):
        for change in [dict(actor_after='b'*64),dict(initial_audit={'passed':False}),dict(max_command_error=1e-5),
            dict(supervisor={'go_issued':True,'process_exit_confirmed':False}),dict(archive_sha256=None)]:
            self.assertIsNone(self.c.next_unit([dict(self.row(),**change)]))
    def test_no_nonzero_evidence_closes_first_12(self):
        rows=[self.row(i) for i in range(12)];rows[3]['nonzero_applied_command_cycles']=0
        self.assertFalse(self.c.dynamic_precheck(rows)['passed']);self.assertIsNone(self.c.next_unit(rows))
    def test_missing_or_reordered_precheck_refused(self):
        self.assertFalse(self.c.dynamic_precheck([self.row(i) for i in range(11)])['passed'])
        with self.assertRaises(ValueError):self.c.next_unit([self.row(1)])
        with self.assertRaises(ValueError):self.c.next_unit([self.row(0),self.row(0)])
    def test_all_42_closes(self):self.assertIsNone(self.c.next_unit([self.row(i) for i in range(42)]))
    def test_cost_caps(self):
        for k,v in [('policy_call_attempts',14501),('tensor_loads',2),('learner_constructions',1),('formal_updates',1),('control_cycles',True),('reset_completed',2)]:
            with self.assertRaises(ValueError):self.c.check_receipt_costs(dict(self.row(),**{k:v}))
        r=self.row();r['policy_calls']=2
        with self.assertRaises(ValueError):self.c.check_receipt_costs(r)
    def test_numeric_certificate_requires_closed_proof(self):
        with self.assertRaises(PermissionError):self.c.check_numeric_result({}, {}, {})
        result=dict(binding_sha256='a'*64,states_sha256=self.c.sha(OUT/'numeric_reference_states.json'),
            equivalent_states=32,policy_calls=64,actor_specs_sha256=self.c.sha(OUT/'actors.json'),passed=True,
            run_id='run-test',grant_sha256='b'*64,nonce='nonce-test',worker_pid=123)
        ledger=dict(status='CLOSED_COMPLETE',binding_sha256='a'*64,grant_sha256='b'*64,run_id='run-test',nonce='nonce-test')
        proof=dict(process_exit_confirmed=True,owned_launcher_exit_confirmed=True,go_issued=True,returncode=0,
            binding_sha256='a'*64,grant_sha256='b'*64,run_id='run-test',nonce='nonce-test',worker_pid=123,
            result_digest=self.c.digest(result),identity_verified=True)
        self.c.check_numeric_result(result,ledger,proof)
        for obj,key,val in [(result,'equivalent_states',31),(result,'binding_sha256','c'*64),(ledger,'status','RUNNING'),(proof,'returncode',1)]:
            saved=obj[key];obj[key]=val
            with self.assertRaises(PermissionError):self.c.check_numeric_result(result,ledger,proof)
            obj[key]=saved
    def test_numeric_proof_cross_run_splice_refused(self):
        result=dict(binding_sha256='a'*64,states_sha256=self.c.sha(OUT/'numeric_reference_states.json'),
            equivalent_states=32,policy_calls=64,actor_specs_sha256=self.c.sha(OUT/'actors.json'),passed=True,
            run_id='run-A',grant_sha256='b'*64,nonce='nonce-A',worker_pid=123)
        ledger=dict(status='CLOSED_COMPLETE',binding_sha256='a'*64,grant_sha256='b'*64,run_id='run-A',nonce='nonce-A')
        proof=dict(process_exit_confirmed=True,owned_launcher_exit_confirmed=True,go_issued=True,returncode=0,
            binding_sha256='a'*64,grant_sha256='b'*64,run_id='run-A',nonce='nonce-A',worker_pid=123,
            result_digest=self.c.digest(result),identity_verified=True)
        self.c.check_numeric_result(result,ledger,proof)
        for obj,key,value in [(result,'run_id','run-B'),(result,'grant_sha256','c'*64),(result,'nonce','nonce-B'),
            (proof,'run_id','run-B'),(proof,'worker_pid',456),(proof,'identity_verified',False),(proof,'result_digest','d'*64)]:
            previous=obj[key];obj[key]=value
            with self.assertRaises(PermissionError):self.c.check_numeric_result(result,ledger,proof)
            obj[key]=previous
    def test_numeric_raw_process_members_and_receipt_bound(self):
        entry=importlib.import_module('sac_entry')
        with tempfile.TemporaryDirectory(dir=OUT,prefix='.numeric_context_') as d:
            run=Path(d);ledger=dict(run_id='run-A',grant_sha256='a'*64,nonce='nonce-A',binding_sha256='b'*64,owner_pid=10)
            raw=dict(process_exit_confirmed=True,owned_launcher_exit_confirmed=True,go_issued=True,returncode=0)
            result=dict(ledger,worker_pid=20)
            receipt=dict(result,status='finished',tensor_load_attempts=2,tensor_loads=2,actor_construction_attempts=2,actor_constructions=2,
                reference_learner_construction_attempts=2,reference_learner_constructions=2,policy_call_attempts=64,policy_calls=64,
                formal_updates=0,optimizer_steps=0,replay_publications=0,native_steps=0)
            members={'gate.supervisor.json':raw,'worker.claim':dict(pid=20,nonce='nonce-A'),
                'gate.ready.json':dict(proof=dict(pid=20),registered_at=123.),
                'gate.go.json':dict(pid=20,parent_pid=10,registered_at=123.,job_assigned=True),
                'result.json':result,'receipt.json':receipt}
            for name,value in members.items():self.c.write(run/name,value)
            proof=entry.numeric_exit_proof(run,ledger,raw);self.assertTrue(proof['identity_verified'])
            self.assertEqual(proof['receipt_sha256'],self.c.sha(run/'receipt.json'))
            for name,key,value in [('worker.claim','nonce','other'),('gate.go.json','pid',30),('gate.go.json','registered_at',456.),
                ('receipt.json','policy_calls',63),('receipt.json','grant_sha256','c'*64)]:
                bad=dict(members[name],**{key:value});self.c.write(run/name,bad)
                self.assertFalse(entry.numeric_exit_proof(run,ledger,raw)['identity_verified'])
                self.c.write(run/name,members[name])
    def test_import_isolation_check(self):
        script="import sys;sys.path.insert(0,"+repr(str(OUT))+");import sac_entry;import torch"
        p=subprocess.run([sys.executable,'-I','-X','utf8','-B','-c',script],capture_output=True,text=True,encoding='utf-8')
        self.assertNotEqual(p.returncode,0);self.assertIn('Scientific import before',p.stderr)
    def test_runtime_calls_without_owned_claim_refused(self):
        runtime=importlib.import_module('actor_runtime')
        for action in [lambda:runtime.load_state({}, {}, {}, lambda:None),lambda:runtime.make_actor({}, {}, {}, {},lambda:None),
            lambda:runtime.actor_digest(None),lambda:runtime.numeric_worker(None,{}, {}, {})]:
            with self.assertRaises(PermissionError):action()
    def test_both_unauthorized_cli_fail_before_execution(self):
        for kind in ['numeric','physical']:
            p=subprocess.run([sys.executable,'-I','-X','utf8','-B',str(OUT/'sac_entry.py'),'--execute','--kind',kind],
                capture_output=True,text=True,encoding='utf-8')
            self.assertNotEqual(p.returncode,0);self.assertIn('Separate explicit numeric/physical grant required',p.stderr)
        self.assertFalse((OUT/'numeric_execution').exists());self.assertFalse((OUT/'evaluation_execution').exists())
    def test_package_exit_recovers_charged_receipt(self):
        entry=importlib.import_module('sac_entry')
        with tempfile.TemporaryDirectory(dir=OUT,prefix='.reconcile_') as d:
            execution=Path(d);run=execution/'case_0';run.mkdir()
            receipt=self.row();receipt['status']='error';receipt['healthy']=False
            self.c.write(run/'receipt.json',receipt)
            ledger=dict(episodes=[dict(index=0,case_id=receipt['case_id'],role=receipt['role'],status='claimed')])
            entry.reconcile(ledger,execution,dict(process_exit_confirmed=True))
            self.assertEqual(ledger['episodes'][0]['reset_attempted'],1)
            self.assertEqual(ledger['episodes'][0]['physical_substeps'],20)
            self.assertTrue(ledger['episodes'][0]['receipt_costs_complete'])
    def test_package_exit_retains_lower_bound_if_worker_interrupted(self):
        entry=importlib.import_module('sac_entry')
        with tempfile.TemporaryDirectory(dir=OUT,prefix='.interrupted_') as d:
            execution=Path(d);run=execution/'case_0';run.mkdir();receipt=self.row();receipt['status']='running'
            self.c.write(run/'receipt.json',receipt)
            ledger=dict(episodes=[dict(index=0,case_id=receipt['case_id'],role=receipt['role'],status='claimed')])
            entry.reconcile(ledger,execution,dict(process_exit_confirmed=True))
            self.assertFalse(ledger['episodes'][0]['receipt_costs_complete'])
            self.assertEqual(ledger['episodes'][0]['reset_attempted'],1)
    def test_source_states_exact_old_inputs(self):
        import gzip,json
        states=self.c.read(OUT/'numeric_reference_states.json')['states'];self.assertEqual(len(states),32)
        groups={}
        for s in states:groups.setdefault(s['source_archive'],[]).append(s)
        self.assertEqual(len(groups),8)
        for path,rows in groups.items():
            self.assertEqual(len(rows),4);self.assertEqual(self.c.sha(path),rows[0]['source_sha256'])
            raw=json.loads(gzip.decompress(Path(path).read_bytes()))
            for r in rows:
                i=r['input_index'];self.assertEqual(r['observation'],raw['transitions'][i]['observation'])
                self.assertEqual(r['raw_action'],raw['actions'][i]['raw_action'])
                self.assertEqual(r['policy_sha256'],raw['policy_sha256'])
    def test_33_reused_42_pending_75(self):
        v=self.c.read(OUT/'reuse_catalog.json')
        self.assertEqual((len(v['pure_B2']),len(v['learned_old']),v['reused'],v['pending'],v['total']),(25,8,33,42,75))
    def test_weight_bytes_manifest_and_old_actor_agree(self):
        for role in ['F0','F2000']:
            a=self.c.actor_spec(role);p=Path(a['checkpoint']);self.assertEqual(self.c.sha(p/'state.pt'),a['state_sha256'])
            self.assertEqual((p/'state.pt').stat().st_size,a['state_bytes']);self.assertEqual(self.c.read(p/'manifest.json')['state_sha256'],a['state_sha256'])
            rows=[r for r in self.c.read(OUT/'numeric_reference_states.json')['states'] if r['role']==role]
            self.assertEqual(len(rows),16);self.assertEqual({r['policy_sha256'] for r in rows},{a['actor_sha256']})

class DriverTests(unittest.TestCase):
    def setUp(self):self.d=importlib.import_module('sac_rollout')
    def fake(self,active=True):
        snap=NS(policy_observation=[0.]*137,residual_enabled=active)
        s=NS(done=False,cycle_id=0,initial_trace_row={'time_s':0},initial=[0.,0.,0.])
        def advance(a):
            s.last_action=a;s.cycle_id+=1;s.done=True
            log=dict(raw_action=a,experience_action=a,requested_residual=[a[0]*5e-5,a[1]*5e-5,0,a[2]*.0005,a[3]*.0005,0],
                applied_residual=[a[0]*5e-5,a[1]*5e-5,0,a[2]*.0005,a[3]*.0005,0],enabled=active,
                effective_command_delta=[a[0]*5e-5,a[1]*5e-5,0,a[2]*.0005,a[3]*.0005,0],
                predicted_limited_command=[a[0]*5e-5,a[1]*5e-5,0,a[2]*.0005,a[3]*.0005,0],
                actual_end_limited_command=[a[0]*5e-5,a[1]*5e-5,0,a[2]*.0005,a[3]*.0005,0])
            return NS(trace_row=dict(time_s=.002,position_m=[0.,0.,0.]),action_log=log,next_snapshot=snap,
                dt=.002,reward_terms={'total':0.},cycle_peaks={'force_N':0.,'torque_G_Nm':0.},done=True)
        s.advance_cycle=advance;return s,snap
    def test_active_predict_and_command_audit(self):
        s,snap=self.fake();receipt={};a=self.d.drive(s,snap,lambda o:[.1,-.2,.3,-.4],receipt,
            permission=lambda o:True,progress=lambda *a:None)
        self.assertEqual(receipt['policy_calls'],1);self.assertEqual(receipt['policy_call_attempts'],1)
        self.assertEqual(receipt['nonzero_applied_command_cycles'],1);self.assertEqual(len(a['transitions']),1)
    def test_inactive_never_predicts(self):
        s,snap=self.fake(False);receipt={}
        self.d.drive(s,snap,lambda o:(_ for _ in ()).throw(AssertionError('predict')),receipt,permission=lambda o:False)
        self.assertEqual(s.last_action,[0.]*4);self.assertEqual(receipt['policy_call_attempts'],0)
    def test_permission_mismatch_before_predict(self):
        s,snap=self.fake(False);receipt={}
        with self.assertRaises(ValueError):self.d.drive(s,snap,lambda o:[0.]*4,receipt,permission=lambda o:True)
        self.assertEqual(s.cycle_id,0)
    def test_failed_prediction_charged(self):
        s,snap=self.fake();r={}
        with self.assertRaises(RuntimeError) as caught:self.d.drive(s,snap,lambda o:(_ for _ in ()).throw(RuntimeError('predict fail')),r,permission=lambda o:True)
        self.assertEqual(r['policy_call_attempts'],1);self.assertEqual(r['policy_calls'],0)
        self.assertEqual(len(caught.exception.episode_partial['trace']),1)
    def test_out_of_range_action_refused(self):
        for value in [[2.,0.,0.,0.],[math.nan]*4,[0.]*3]:
            s,snap=self.fake()
            with self.assertRaises(ValueError):self.d.drive(s,snap,lambda o:value,{},permission=lambda o:True)
            self.assertEqual(s.cycle_id,0)
    def test_cycle_stop_before_predict(self):
        s,snap=self.fake();s.cycle_id=14500
        with self.assertRaises(RuntimeError):self.d.drive(s,snap,lambda o:[0.]*4,{},permission=lambda o:True)
    def test_command_drift_refused(self):
        s,snap=self.fake();old=s.advance_cycle
        def bad(a):
            r=old(a);r.action_log['actual_end_limited_command'][0]+=.001;return r
        s.advance_cycle=bad
        with self.assertRaises(ValueError):self.d.drive(s,snap,lambda o:[.1]*4,{},permission=lambda o:True)
    def test_first_cycle_failure_preserves_latest_physical_facts(self):
        env=NS(events=[{'time':.001,'reason':'GUARD'}],stop_samples=[{'time':.001}],guard_facts={'simulation_valid':False},
            phase='STOPPING',physical_steps=7,data=NS(time=.001))
        session=NS(stop_time=.001,task_end_time=None,task_finished=False,reason='GUARD',cycle_id=0,controller=NS(events=[{'reason':'finish'}]))
        raw=self.d.failure_archive(dict(trace=[{}],actions=[],transitions=[]),env,session,{},RuntimeError('fault'))
        self.assertEqual(raw['events'],env.events);self.assertEqual(raw['stop_samples'],env.stop_samples)
        self.assertEqual(raw['physical_substeps'],7);self.assertEqual(raw['stop_time'],.001)
        self.assertEqual(raw['controller_events'],session.controller.events);self.assertEqual(raw['final_session']['reason'],'GUARD')
        self.assertEqual(raw['missing_fields'],[])
        env.events.append({'late':True});self.assertEqual(len(raw['events']),1)
    def test_late_failure_uses_current_not_partial_snapshot(self):
        env=NS(events=[{'cycle':501}],stop_samples=[{'cycle':501}],guard_facts={},phase='STOPPING',physical_steps=5010,data=NS(time=1.002))
        session=NS(stop_time=1.002,task_end_time=1.,task_finished=False,reason='stop',cycle_id=501,controller=NS(events=[]))
        raw=self.d.failure_archive(dict(trace=[],actions=[],transitions=[],events=[{'cycle':500}]),env,session,{},ValueError('bad'))
        self.assertEqual(raw['events'],[{'cycle':501}]);self.assertEqual(raw['control_cycles'],501)
    def test_unconstructed_failure_explicitly_marks_missing(self):
        raw=self.d.failure_archive({},None,None,{},ValueError('init'))
        self.assertIsNone(raw['events']);self.assertIn('events',raw['missing_fields']);self.assertIn('final_session',raw['missing_fields'])

class RebindingTests(unittest.TestCase):
    def test_changed_binding_invalidates_old_pass_flags(self):
        sys.path.insert(0,str(OUT));f=importlib.import_module('finalize_sources')
        previous=dict(source_binding_sha256='a'*64,offline_checks_passed=True,fresh_review_completed=True)
        self.assertEqual(f.retained_checks(previous,'b'*64),dict(offline_checks_passed=False,fresh_review_completed=False))
        self.assertEqual(f.retained_checks(previous,'a'*64),dict(offline_checks_passed=True,fresh_review_completed=True))

if __name__=='__main__':unittest.main(verbosity=2)
