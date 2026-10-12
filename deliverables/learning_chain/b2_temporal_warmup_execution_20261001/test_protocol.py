import copy,importlib,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
try:C=importlib.import_module('execution_contract')
except ModuleNotFoundError as e:
    if e.name!='execution_contract':raise
    C=None
try:S=importlib.import_module('sampling_runtime')
except ModuleNotFoundError as e:
    if e.name!='sampling_runtime':raise
    S=None
try:R=importlib.import_module('run_preflight')
except ModuleNotFoundError as e:
    if e.name!='run_preflight':raise
    R=None

def snapshot(i,phase='INSERT',active=True):
    v=[0.]*120;v[53+('INSERT','UNLOAD','SEARCH','WAIT_RECOVERY','FAILED').index(phase)]=1.;v[76]=float(active)
    return SimpleNamespace(cycle_id=i,controller_state={'phase':phase},residual_enabled=active,policy_observation=v)

class ContractTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(C,'Missing independent preflight contract')
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'ledger.json';self.pin='a'*64;self.auth='b'*64
    def ledger(self):return C.Ledger.create(self.path,self.pin,self.auth)
    def row(self,i=0,**kw):
        r=dict(**C.attempts()[i],completed=True,success=False,simulation_valid=True,physical_stopped=True,
            guard_hit=False,cycles=50,draw_count=50 if i%2==0 else 1,model_forwards=0,training_batches=0)
        r.update(kw);return r
    def test_pair_order_exact(self):
        ids=[x['id'] for x in C.attempts()]
        self.assertEqual(ids,['x_pos_100_A','x_pos_100_C','x_neg_100_A','x_neg_100_C','y_pos_100_A','y_pos_100_C','y_neg_100_A','y_neg_100_C'])
    def test_scope_zero_learning_and_eight_new_starts(self):
        s=C.scope();self.assertEqual((s['dynamic_cap'],s['previous_dynamic'],s['cumulative_dynamic_cap'],s['training_batches'],s['model_forwards']),(8,60,68,0,0))
    def test_reserve_before_first_start(self):
        l=self.ledger();l.start(C.attempts()[0]['id']);a=l.accounting()
        self.assertEqual((a['new_dynamic_starts'],a['control_cycles_reserved'],a['cumulative_dynamic']),(1,13000,61))
    def test_wrong_order_or_second_active_start_refused(self):
        l=self.ledger()
        with self.assertRaises(RuntimeError):l.start(C.attempts()[1]['id'])
        l.start(C.attempts()[0]['id'])
        with self.assertRaises(RuntimeError):l.start(C.attempts()[1]['id'])
    def test_ordinary_failure_allows_next(self):
        l=self.ledger();l.start(C.attempts()[0]['id']);l.finish(self.row());l.start(C.attempts()[1]['id'])
        self.assertEqual(l.accounting()['new_dynamic_starts'],2)
    def test_any_valid_guard_stops_remainder(self):
        l=self.ledger();l.start(C.attempts()[0]['id']);l.finish(self.row(guard_hit=True))
        self.assertEqual(l.state['status'],'stopped')
        with self.assertRaises(RuntimeError):l.start(C.attempts()[1]['id'])
    def test_invalid_or_unstopped_is_failed(self):
        for i,kw in enumerate(({'simulation_valid':False},{'physical_stopped':False})):
            p=Path(self.tmp.name)/('invalid_'+str(i)+'.json');l=C.Ledger.create(p,self.pin,self.auth)
            l.start(C.attempts()[0]['id']);l.finish(self.row(**kw));self.assertEqual(l.state['status'],'failed')
    def test_finish_cannot_forge_another_identity(self):
        l=self.ledger();l.start(C.attempts()[0]['id'])
        with self.assertRaises(ValueError):l.finish(self.row(1))
    def test_result_rejects_invalid_accounting(self):
        for kw in ({'cycles':13001},{'cycles':True},{'draw_count':51},{'model_forwards':1},{'training_batches':1}):
            with self.assertRaises(ValueError):C.validate_result(self.row(**kw))
    def test_duplicate_finish_rejected(self):
        l=self.ledger();l.start(C.attempts()[0]['id']);l.finish(self.row())
        with self.assertRaises(RuntimeError):l.finish(self.row())
    def test_stale_ledger_cannot_mutate(self):
        l=self.ledger();q=C.Ledger.load(self.path,self.pin,self.auth);l.start(C.attempts()[0]['id'])
        with self.assertRaises(RuntimeError):q.start(C.attempts()[0]['id'])
    def test_complete_needs_all_eight(self):
        l=self.ledger()
        with self.assertRaises(RuntimeError):l.complete()
        for i,a in enumerate(C.attempts()):l.start(a['id']);l.finish(self.row(i))
        l.complete();self.assertEqual(l.state['status'],'complete');self.assertEqual(l.accounting()['control_cycles_reserved'],104000)
    def test_fault_charged_and_active_cleared(self):
        l=self.ledger();l.start(C.attempts()[0]['id']);l.fail('test fault')
        self.assertEqual((l.state['status'],l.state['active'],l.accounting()['new_dynamic_starts']),('failed',None,1))
    def test_cross_authorization_restore_refused(self):
        self.ledger()
        with self.assertRaises(ValueError):C.Ledger.load(self.path,self.pin,'c'*64)
    def test_authorization_scope_must_be_exact(self):
        a=dict(version='temporal_preflight_authorization_v1',approved=True,binding_sha256=self.pin,scope=C.scope(),user_confirmation='继续')
        C.validate_authorization(a,self.pin)
        for field,value in [('dynamic_cap',9),('training_batches',1),('stop_on_any_guard',False)]:
            b=copy.deepcopy(a);b['scope'][field]=value
            with self.assertRaises(ValueError):C.validate_authorization(b,self.pin)
    def test_write_fault_poisoned_without_budget_reuse(self):
        l=self.ledger();original=C.write
        def fail(*a):raise OSError('disk fault')
        C.write=fail
        try:
            with self.assertRaises(OSError):l.start(C.attempts()[0]['id'])
        finally:C.write=original
        with self.assertRaises(RuntimeError):l.start(C.attempts()[0]['id'])

class SamplingTests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(S,'Missing live-context sampler integration')
    def schedule(self,i=1,check=lambda:None):return S.Schedule(C.attempts()[i],check)
    def test_paired_initial_rng_equal(self):
        a=self.schedule(0);c=self.schedule(1)
        self.assertEqual(a.capture()['rng_initial'],c.capture()['rng_initial'])
        self.assertEqual(a.act(snapshot(0),snapshot(0).policy_observation),c.act(snapshot(0),snapshot(0).policy_observation))
    def test_50_cycle_hold_in_live_context(self):
        c=self.schedule();actions=[c.act(snapshot(i),snapshot(i).policy_observation) for i in range(51)]
        self.assertTrue(all(a==actions[0] for a in actions[:50]));self.assertNotEqual(actions[50],actions[0])
    def test_current_permission_closes_old_hold(self):
        c=self.schedule();c.act(snapshot(0),snapshot(0).policy_observation)
        s=snapshot(1,'UNLOAD',False);self.assertEqual(c.act(s,s.policy_observation),[0.]*4)
        c.act(snapshot(2),snapshot(2).policy_observation);self.assertEqual(c.capture()['sampler']['draw_count'],2)
    def test_stage_change_redraws(self):
        c=self.schedule();c.act(snapshot(0),snapshot(0).policy_observation)
        s=snapshot(1,'SEARCH');c.act(s,s.policy_observation);self.assertEqual(c.capture()['sampler']['draw_count'],2)
    def test_observation_and_permission_disagreement_refused(self):
        for field in ('permission','phase','oldobs'):
            c=self.schedule();s=snapshot(0);expected=s.policy_observation.copy()
            if field=='permission':s.residual_enabled=False
            elif field=='phase':s.controller_state['phase']='SEARCH'
            else:expected[0]=1
            with self.assertRaises(ValueError):c.act(s,expected)
            self.assertEqual(c.capture()['sampler']['draw_count'],0)
    def test_supervision_checked_before_random_draw(self):
        def fail():raise RuntimeError('parent stopped')
        c=self.schedule(check=fail)
        with self.assertRaises(RuntimeError):c.act(snapshot(0),snapshot(0).policy_observation)
        self.assertEqual(c.capture()['sampler']['draw_count'],0)
    def test_complete_sampler_rng_restoration(self):
        c=self.schedule()
        for i in range(27):c.act(snapshot(i),snapshot(i).policy_observation)
        restored=S.Schedule.restore(json.loads(json.dumps(c.capture())),lambda:None)
        for i in range(27,110):self.assertEqual(c.act(snapshot(i),snapshot(i).policy_observation),restored.act(snapshot(i),snapshot(i).policy_observation))
    def test_wrong_rng_draw_count_refused(self):
        c=self.schedule();c.act(snapshot(0),snapshot(0).policy_observation);s=c.capture()
        s['rng_final']['state']['state']+=1
        with self.assertRaises(ValueError):S.Schedule.restore(s,lambda:None)
    def test_cross_case_or_hold_identity_refused(self):
        c=self.schedule();s=c.capture();s['identity']['hold_cycles']=1
        with self.assertRaises(ValueError):S.Schedule.restore(s,lambda:None)
    def test_metadata_before_and_after_cycle_is_explicit(self):
        c=self.schedule();s=snapshot(0);action=c.act(s,s.policy_observation);r=c.records[0]
        self.assertEqual(r['action'],action);self.assertEqual(r['cycle_id'],0);self.assertEqual(r['policy_phase'],'INSERT');self.assertEqual(r['remaining'],49)
    def test_cached_context_taken_before_action(self):
        c=self.schedule();order=[];s=snapshot(0)
        class Fake:
            def prepare_cycle(self):order.append('snapshot');return s
        policy=S.ContextPolicy(Fake(),c);p=policy.predict(s.policy_observation)
        self.assertEqual(order,['snapshot']);self.assertEqual(len(c.records),1);self.assertEqual(list(p[0]),c.records[0]['action'])
    def test_training_style_or_truncation_entry_refused(self):
        with self.assertRaises(ValueError):S.require_collection_mode(cut_at_end=True,deterministic=True)
        with self.assertRaises(ValueError):S.require_collection_mode(cut_at_end=False,deterministic=False)

class EntryTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(R,'Missing supervised physical preflight entry')
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.ledger=C.Ledger.create(Path(self.tmp.name)/'ledger.json','a'*64,'b'*64)
    def test_physics_refused_before_reservation(self):
        b=R.PhysicsBudget(self.ledger);calls=[]
        with self.assertRaises(RuntimeError):b.step(lambda *a,**k:calls.append(1),None,None)
        self.assertEqual(calls,[])
    def test_physics_charge_before_call_and_episode_limit(self):
        l=self.ledger;l.start(C.attempts()[0]['id']);b=R.PhysicsBudget(l);b.begin();calls=[]
        def step(*a,**k):calls.append(b.episode_substeps)
        b.step(step,None,None);self.assertEqual(calls,[1]);b.episode_substeps=130000
        with self.assertRaises(RuntimeError):b.step(step,None,None)
        self.assertEqual(calls,[1])
    def test_batched_physics_step_refused(self):
        self.ledger.start(C.attempts()[0]['id']);b=R.PhysicsBudget(self.ledger);b.begin()
        with self.assertRaises(ValueError):b.step(lambda *a,**k:None,None,None,nstep=2)
    def test_initialization_after_guard_stop_refused(self):
        l=self.ledger;l.start(C.attempts()[0]['id']);b=R.PhysicsBudget(l);b.begin()
        row=dict(**C.attempts()[0],completed=True,success=False,simulation_valid=True,physical_stopped=True,
            guard_hit=True,cycles=10,draw_count=1,model_forwards=0,training_batches=0)
        l.finish(row)
        with self.assertRaises(RuntimeError):b.initialize('reset',lambda *a:None,None)
    def test_authorization_before_runtime_selection(self):
        original=R.require_authorization;select=R.select_runtime;calls=[]
        def no(*a):raise ValueError('not authorized')
        R.require_authorization=no;R.select_runtime=lambda:calls.append('runtime')
        try:
            with self.assertRaises(ValueError):R.main(['--binding-sha256','a'*64,'--authorization-sha256','b'*64,'--worker'])
        finally:R.require_authorization=original;R.select_runtime=select
        self.assertEqual(calls,[])
    def test_stop_tail_includes_total_cycle_cap(self):
        cls=R.collector_type();c=object.__new__(cls)
        class Fake:
            done=False;cycle_id=12999
            def start_external_tail(self):pass
            def prepare_cycle(self):return snapshot(self.cycle_id,'FAILED',False)
            def advance_cycle(self,a):
                self.cycle_id+=1
                return SimpleNamespace(next_snapshot=snapshot(self.cycle_id,'FAILED',False),done=False,dt=.002,
                    reward_terms={'total':0},action_log={'experience_action':[0.]*4},trace_row={},events=[])
        c.session=Fake()
        c.admission=SimpleNamespace(ledger=self.ledger)
        with self.assertRaises(RuntimeError):c._stop_tail()
        self.assertEqual(c.session.cycle_id,13000)
    def test_tail_checks_current_supervisor_before_every_cycle(self):
        cls=R.collector_type();c=object.__new__(cls);calls=[]
        class Fake:
            done=False;cycle_id=4
            def start_external_tail(self):pass
            def advance_cycle(self,a):calls.append('physical');self.done=True
        def reject():raise RuntimeError('supervisor gone')
        c.session=Fake();c.admission=SimpleNamespace(ledger=SimpleNamespace(check_live=reject))
        with self.assertRaises(RuntimeError):c._stop_tail()
        self.assertEqual(calls,[])
    def test_fault_tail_transitions_are_retained_separately(self):
        cls=R.collector_type();c=object.__new__(cls)
        before=snapshot(8,'FAILED',False);after=snapshot(9,'FAILED',False)
        class Fake:
            done=False;cycle_id=8
            def start_external_tail(self):pass
            def prepare_cycle(self):return before
            def advance_cycle(self,a):
                self.done=True;self.cycle_id+=1
                return SimpleNamespace(next_snapshot=after,done=True,dt=.002,reward_terms={'total':0},
                    action_log={'experience_action':[0.]*4},trace_row={'time_s':.018},events=[])
        c.session=Fake();c.admission=SimpleNamespace(ledger=SimpleNamespace(check_live=lambda:None))
        c._stop_tail()
        self.assertEqual(len(getattr(c,'fault_tail_transitions',[])),1)
        self.assertEqual(c.fault_tail_transitions[0]['observation'],before.policy_observation)
    def test_substep_forward_uses_local_permit_without_million_live_checks(self):
        self.ledger.start(C.attempts()[0]['id']);calls=[]
        original=self.ledger.check_live
        self.ledger.check_live=lambda:(calls.append('live'),original())[1]
        b=R.PhysicsBudget(self.ledger);b.begin()
        self.assertTrue(hasattr(b,'forward'),'Separate per-substep forward permit required')
        b.initialize('reset',lambda:None);b.forward(lambda:None)
        initial=len(calls);b.step(lambda *a:None,None,None);b.forward(lambda:None)
        self.assertEqual(len(calls),initial)
        self.assertEqual(b.substep_forwards,1)

class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(R)
        from unittest.mock import patch
        from tools.learning.audited_replay import AuditedReplay
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.audit=patch('tools.learning.sac_checkpoint._audit_physics',return_value=None)
        self.audit.start();self.addCleanup(self.audit.stop)
        self.rule=patch('tools.learning.episode_rules.FORCE_ONLY.classify',return_value={'kind':'guard_clear'})
        self.rule.start();self.addCleanup(self.rule.stop)
        cls=R.collector_type();self.collector=object.__new__(cls);c=self.collector
        c._folder=Path(self.tmp.name);c._status_pending=False;c._blocked=True;c._record={}
        c.admission=SimpleNamespace(verify=lambda case:None);c.replay=AuditedReplay(capacity=13000)
        c.schedule=S.Schedule(C.attempts()[0],lambda:None);s=snapshot(0);action=c.schedule.act(s,s.policy_observation)
        row=dict(observation=s.policy_observation,next_observation=snapshot(1,'FAILED',False).policy_observation,
            action=action,action_active=True,next_action_active=False,dt=.002,discount=__import__('math').exp(-.002/10),
            reward=0.,terminated=True,truncated=False,action_log={'raw_action':action})
        c._pending=dict(episode_id=C.attempts()[0]['id'],case=C.attempts()[0]['case'],transitions=[row],fault=None,
            guard_facts=dict(simulation_valid=True,contact_reasons=[],motion_reasons=[],invalid_reasons=[]),
            outcome=dict(simulation_valid=True,physical_stopped=True,valid_for_learning=True,
                guard_violations={'contact':False,'motion':False},task_outcome='TASK_FAILURE'))
        c.session=object();c.buffer=object()
    def test_complete_preflight_archives_without_replay_publication(self):
        c=self.collector;c.retry_publication()
        self.assertEqual(c._record['committed'],0);self.assertEqual(len(c.replay),0)
        self.assertEqual(c._record['discarded'],1);self.assertFalse(c._blocked)
        self.assertTrue((c._folder/'episode.json.gz').exists());self.assertIsNone(c.session)
    def test_archive_precedes_audit_failure(self):
        self.audit.stop()
        from unittest.mock import patch
        with patch('tools.learning.sac_checkpoint._audit_physics',side_effect=ValueError('bad audit')):
            cls=R.collector_type();self.collector.__class__=cls
            with self.assertRaises(ValueError):self.collector.retry_publication()
        self.assertTrue((self.collector._folder/'episode.json.gz').exists())
        self.assertEqual(len(self.collector.replay),0)
    def test_other_guard_retained_as_valid_stopped_result(self):
        c=self.collector;c._pending['guard_facts']['contact_reasons']=['PENETRATION_LIMIT']
        c._pending['outcome'].update(task_outcome='CONTACT_GUARD',valid_for_learning=False,guard_violations={'contact':True,'motion':False})
        c.retry_publication();self.assertEqual(c._record['rule_audit'],'other_guard_stop');self.assertFalse(c._blocked)
        self.assertEqual(c._record['committed'],0)

if __name__=='__main__':unittest.main()
