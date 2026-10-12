import copy,importlib,json,unittest
try: module=importlib.import_module('warmup_hold')
except ModuleNotFoundError as exc:
    if exc.name!='warmup_hold':raise
    module=None

class Draws:
    def __init__(self):self.n=0
    def __call__(self):
        self.n+=1
        return [(.25 if self.n%2 else -.75),.2,-.3,.4]

class HoldTests(unittest.TestCase):
    def make(self,n=50,draw=None):
        self.assertIsNotNone(module,'The temporal warmup behavior has not been implemented')
        draw=draw or Draws();return module.WarmupHold(draw,hold_cycles=n),draw
    def test_exact_100ms_holds_and_redraws(self):
        p,d=self.make();a=[p.next(i,'INSERT',True) for i in range(51)]
        self.assertTrue(all(r['action']==a[0]['action'] for r in a[:50]));self.assertNotEqual(a[50]['action'],a[0]['action']);self.assertEqual(d.n,2)
    def test_two_ms_control_matches_each_supplied_draw(self):
        p,d=self.make(1)
        self.assertEqual([p.next(i,'INSERT',True)['action'][0] for i in range(4)],[.25,-.75,.25,-.75]);self.assertEqual(d.n,4)
    def test_no_draw_in_inactive_cycles_and_immediate_zero(self):
        p,d=self.make();p.next(0,'INSERT',True)
        r=p.next(1,'WAIT_RECOVERY',False);self.assertEqual(r['action'],[0.]*4);self.assertEqual(d.n,1)
        p.next(2,'FAILED',False);self.assertEqual(d.n,1)
    def test_reentry_redraws_instead_of_reusing_stale_action(self):
        p,d=self.make();a=p.next(0,'INSERT',True);p.next(1,'UNLOAD',False)
        b=p.next(2,'INSERT',True);self.assertNotEqual(a['action'],b['action']);self.assertTrue(b['redrawn'])
    def test_insert_search_transition_starts_new_block(self):
        p,d=self.make();a=p.next(0,'INSERT',True);b=p.next(1,'SEARCH',True)
        self.assertNotEqual(a['action'],b['action']);self.assertEqual(d.n,2)
    def test_equal_context_opposite_hidden_case_cannot_change_output(self):
        p,_=self.make();q,_=self.make()
        self.assertEqual([p.next(i,'INSERT',True) for i in range(70)],[q.next(i,'INSERT',True) for i in range(70)])
    def test_returned_action_cannot_mutate_held_value(self):
        p,_=self.make();p.next(0,'INSERT',True)['action'][0]=1
        self.assertEqual(p.next(1,'INSERT',True)['action'][0],.25)
    def test_context_rejects_repeated_skipped_and_invalid_cycles_before_draw(self):
        p,d=self.make();p.next(0,'INSERT',True)
        for bad in (0,2,-1,True,1.0):
            with self.assertRaises(ValueError):p.next(bad,'INSERT',True)
        self.assertEqual(d.n,1);p.next(1,'INSERT',True)
    def test_invalid_permission_or_phase_refused_without_draw(self):
        p,d=self.make()
        for phase,enabled in [('UNLOAD',True),('STOPPING',True),('UNKNOWN',False),('INSERT',1)]:
            with self.assertRaises(ValueError):p.next(0,phase,enabled)
        self.assertEqual(d.n,0)
    def test_bad_rng_output_poisoned_and_not_retried(self):
        for bad in ([float('nan')]*4,[2,0,0,0],[0]*3,[True,0,0,0]):
            p,_=self.make(draw=lambda:bad)
            with self.assertRaises(ValueError):p.next(0,'INSERT',True)
            with self.assertRaises(RuntimeError):p.next(0,'INSERT',True)
    def test_rng_exception_poisoned_and_not_retried(self):
        def bad():raise OSError('source failed')
        p,_=self.make(draw=bad)
        with self.assertRaises(OSError):p.next(0,'INSERT',True)
        with self.assertRaises(RuntimeError):p.next(0,'INSERT',True)
    def test_snapshot_and_external_rng_restore_agree(self):
        p,d=self.make()
        for i in range(23):p.next(i,'INSERT',True)
        saved=json.loads(json.dumps(p.snapshot()));qdraw=Draws();qdraw.n=d.n
        q=module.WarmupHold.restore(qdraw,saved,expected_hold_cycles=50)
        self.assertEqual([p.next(i,'INSERT',True) for i in range(23,110)],[q.next(i,'INSERT',True) for i in range(23,110)])
    def test_snapshot_tamper_and_cross_config_refused(self):
        p,_=self.make();p.next(0,'INSERT',True);s=p.snapshot()
        for key,bad in [('remaining',50),('last_cycle',True),('phase','UNLOAD'),('action',[2]*4),('draw_count',-1),('version','other')]:
            v=copy.deepcopy(s);v[key]=bad
            with self.assertRaises(ValueError):module.WarmupHold.restore(Draws(),v,expected_hold_cycles=50)
        with self.assertRaises(ValueError):module.WarmupHold.restore(Draws(),s,expected_hold_cycles=1)
    def test_unregistered_hold_duration_refused(self):
        self.assertIsNotNone(module,'The temporal warmup behavior has not been implemented')
        for value in (0,2,10,100,True,50.0):
            with self.assertRaises(ValueError):module.WarmupHold(Draws(),hold_cycles=value)
    def test_restore_cannot_shorten_first_held_block(self):
        p,_=self.make();p.next(0,'INSERT',True)
        for remaining in (0,10,48):
            s=p.snapshot();s['remaining']=remaining
            with self.assertRaises(ValueError):module.WarmupHold.restore(Draws(),s,expected_hold_cycles=50)
    def test_restore_rejects_draw_before_only_inactive_cycle(self):
        p,_=self.make();p.next(0,'INSERT',True);s=p.snapshot()
        s.update(phase=None,action=None,remaining=0)
        with self.assertRaises(ValueError):module.WarmupHold.restore(Draws(),s,expected_hold_cycles=50)
    def test_restore_rejects_too_few_draws_before_current_block(self):
        p,_=self.make();p.next(0,'INSERT',True);s=p.snapshot()
        s.update(last_cycle=99,block_start_cycle=99,remaining=49,active_cycles=100,draw_count=2)
        with self.assertRaises(ValueError):module.WarmupHold.restore(Draws(),s,expected_hold_cycles=50)
    def test_whole_episode_13000_cycle_cap(self):
        p,d=self.make()
        for i in range(13000):p.next(i,'INSERT',True)
        self.assertEqual(d.n,260)
        with self.assertRaises(RuntimeError):p.next(13000,'INSERT',True)

if __name__=='__main__':unittest.main()
