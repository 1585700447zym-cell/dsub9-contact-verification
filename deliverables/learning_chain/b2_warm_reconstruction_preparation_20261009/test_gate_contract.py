from pathlib import Path
import copy,json,sys,tempfile,time,unittest,uuid
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
from gate_contract import LIMITS,verify_grant,Counter,require_zero_metadata,require_warm_metadata,verify_reply
from joint_contract import digest,read,write

def zero():
    return dict(attempts=[],archives={},history=[],update_attempts=0,stop_reason=None,journal='',
        warm=dict(draws=0,held=[0.]*4),replay=dict(size=0),updater=dict(counts=dict(critic=0,actor=0,temperature=0,target=0)))

class GateTests(unittest.TestCase):
    def setUp(self):
        self.folder=HERE/'test_work'/uuid.uuid4().hex;self.folder.mkdir(parents=True)
        self.candidate=dict(status='PREPARED_NOT_AUTHORIZED',training_admitted=False,numeric_verified=False)
        self.grant=dict(version='b2_warm_restore_grant_v1',status='OPEN',explicit_user_authorized=True,human_evidence='批准本次具体数值门',
            candidate_sha256=digest(self.candidate),binding_sha256='a'*64,limits=copy.deepcopy(LIMITS),cumulative_before=245,
            whole_wall_s=1800,reader_wall_s=900)

    def test_unsigned_grant_refused(self):
        self.grant['explicit_user_authorized']=False
        with self.assertRaises(PermissionError):verify_grant(self.candidate,self.grant,digest(self.grant),'a'*64)

    def test_training_allowance_or_wrong_source_refused(self):
        g=copy.deepcopy(self.grant);g['limits']['formal_updates']=1
        with self.assertRaises(ValueError):verify_grant(self.candidate,g,digest(g),'a'*64)
        g=copy.deepcopy(self.grant);g['binding_sha256']='b'*64
        with self.assertRaises(ValueError):verify_grant(self.candidate,g,digest(g),'a'*64)

    def test_exact_grant_allowed(self):
        verify_grant(self.candidate,self.grant,digest(self.grant),'a'*64)

    def test_expanded_wall_refused(self):
        self.grant['whole_wall_s']=1801
        with self.assertRaises(ValueError):verify_grant(self.candidate,self.grant,digest(self.grant),'a'*64)

    def test_corrupt_negative_counter_refused(self):
        c=Counter.create(self.folder/'counter.json');c.claim('parent')
        d=read(c.path);d['attempted']['tensor_loads']=-1;write(c.path,d)
        with self.assertRaises(ValueError):c.take('parent','tensor_loads')

    def test_incomplete_accounting_cannot_complete(self):
        c=Counter.create(self.folder/'counter.json');c.claim('parent')
        with self.assertRaises(ValueError):c.require_complete()

    def test_complete_accounting_requires_both_roles(self):
        from gate_contract import ROLE_LIMITS
        c=Counter.create(self.folder/'counter.json')
        for role,limits in ROLE_LIMITS.items():
            c.claim(role)
            for key,n in limits.items():
                for _ in range(n):c.take(role,key)
        c.require_complete()

    def test_roles_share_bounds_and_cannot_restart(self):
        c=Counter.create(self.folder/'counter.json');c.claim('parent');c.take('parent','learner_constructions')
        with self.assertRaises(PermissionError):c.claim('parent')
        with self.assertRaises(PermissionError):c.take('parent','learner_constructions')
        c.claim('reader');c.take('reader','learner_constructions')
        self.assertEqual(read(c.path)['attempted']['learner_constructions'],2)

    def test_zero_limits_and_unclaimed_role_refused(self):
        c=Counter.create(self.folder/'counter.json')
        with self.assertRaises(PermissionError):c.take('parent','tensor_loads')
        c.claim('parent')
        for key in ('formal_updates','physical_episodes','new_experience'):
            with self.assertRaises(PermissionError):c.take('parent',key)

    def test_close_expires_every_remaining_operation(self):
        c=Counter.create(self.folder/'counter.json');c.claim('parent');c.take('parent','tensor_loads');c.close()
        with self.assertRaises(PermissionError):c.take('parent','checkpoint_saves')
        d=read(c.path);self.assertEqual(d['unused_closed']['tensor_loads'],1);self.assertEqual(d['status'],'CLOSED')

    def test_closure_receipt_revokes_even_an_open_counter(self):
        from gate_contract import Gate
        from joint_contract import sha
        gate=object.__new__(Gate);gate.folder=self.folder;gate.candidate=self.candidate
        gate.binding_pin=sha(HERE/'source_binding.json');self.grant['binding_sha256']=gate.binding_pin
        gate.pin=digest(self.grant);write(self.folder/'grant.json',self.grant)
        gate.counter=Counter.create(self.folder/'counter.json')
        write(self.folder/'authorization_closure.json',dict(status='CLOSED_ERROR',counter_closed=False))
        with self.assertRaisesRegex(PermissionError,'closed authorization'):gate.verify()
        self.assertEqual(read(gate.counter.path)['status'],'OPEN')

    def test_zero_checkpoint_with_history_is_rejected(self):
        z=zero();require_zero_metadata(z)
        z['history']=[{'old':1}]
        with self.assertRaises(ValueError):require_zero_metadata(z)

    def test_restored_boundary_cannot_claim_online_or_updates(self):
        z=zero();z.update(attempts=[dict(episode_id='warmup_F50_J0'+str(i),stage='warmup',case_index=i-1) for i in range(1,5)],
            archives={'warmup_F50_J0'+str(i):b'x' for i in range(1,5)},warm=dict(draws=388,held=[.1]*4),replay=dict(size=19300))
        require_warm_metadata(z)
        z['updater']['counts']['critic']=1
        with self.assertRaises(ValueError):require_warm_metadata(z)

    def test_reader_mismatch_never_qualifies(self):
        with self.assertRaises(ValueError):verify_reply('a'*64,dict(state_digest='b'*64,verified=True))
        with self.assertRaises(ValueError):verify_reply('a'*64,dict(state_digest='a'*64,verified=False))
        verify_reply('a'*64,dict(state_digest='a'*64,verified=True))

if __name__=='__main__':unittest.main(verbosity=2)
