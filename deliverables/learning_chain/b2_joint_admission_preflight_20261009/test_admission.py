"""Admission and budget negative tests; injected invocation never simulates."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import tempfile
from contextlib import contextmanager
import uuid
import unittest
from copy import deepcopy
from scope_contract import proposal,PROPOSAL_PIN,attempt_specs
from execution_contract import validate_grant,execute_matrix,claim_once

@contextmanager
def scratch():
    p=Path(__file__).resolve().parents[3]/'tmp'/'b2_joint_offline_tests'/uuid.uuid4().hex
    p.mkdir(parents=True);yield str(p)

class AdmissionTests(unittest.TestCase):
    def grant(self):
        c=proposal()
        return dict(version='b2_joint_preflight_grant_v1',status='OPEN',explicit_user_approval=True,
            binding_sha256='a'*64,proposal_sha256=PROPOSAL_PIN,scope_key=c['draft_scope_key'],
            limits=c['proposed_limits'],authorization_text='synthetic offline fixture, never executable')
    def test_new_grant_and_reject_old_or_request(self):
        g=self.grant();validate_grant(g,'a'*64,proposal())
        for key,val in [('version','b2_pose_scope_grant_v1'),('explicit_user_approval',False),('status','REQUESTED_NOT_AUTHORIZED'),('binding_sha256','b'*64),('authorization_text','')]:
            bad=deepcopy(g);bad[key]=val
            with self.assertRaises(ValueError):validate_grant(bad,'a'*64,proposal())
        bad=deepcopy(g);bad['limits']['dynamic_attempts']=13
        with self.assertRaises(ValueError):validate_grant(bad,'a'*64,proposal())
    def result(self,guard=False):
        return dict(status='finished',audit_passed=True,physical_substeps_lower_bound=20,physical_substeps_upper_bound=20,
            outcome=dict(simulation_valid=True,physical_stopped=True,task_outcome='CONTACT_GUARD' if guard else 'TASK_FAILURE',
            guard_violations=dict(contact=guard,motion=False)))
    def test_fixed_12_and_reservation_before_invoke(self):
        with scratch() as t:
            seen=[]
            def invoke(spec,entry):
                from scope_contract import read
                live=read(Path(t)/'ledger.json');self.assertEqual(live['dynamic_attempts'],len(seen)+1)
                self.assertEqual(entry['status'],'running');seen.append(spec['id']);return self.result()
            ledger=execute_matrix(proposal(),t,invoke)
            self.assertEqual(len(seen),12);self.assertEqual(ledger['status'],'CLOSED_COMPLETE')
            self.assertEqual(ledger['unused_static_closed'],0);self.assertEqual(ledger['unused_dynamic_closed'],0)
    def test_guard_error_and_no_retry(self):
        for failure in ('guard','error'):
            with scratch() as t:
                def invoke(*args):
                    if failure=='error':raise TimeoutError('synthetic deadline')
                    return self.result(True)
                ledger=execute_matrix(proposal(),t,invoke)
                self.assertEqual(ledger['dynamic_attempts'],1);self.assertEqual(ledger['unused_dynamic_closed'],11)
                self.assertNotEqual(ledger['status'],'CLOSED_COMPLETE')
    def test_single_claim_and_existing_output_rejected(self):
        with scratch() as t:
            p=Path(t);claim_once(p/'claims','a'*64,p/'one',{'binding_sha256':'x'})
            with self.assertRaises(FileExistsError):claim_once(p/'claims','a'*64,p/'two',{})
            with self.assertRaises(FileExistsError):claim_once(p/'claims','c'*64,p/'three',{})
            self.assertFalse((p/'two').exists())
            with self.assertRaises(FileExistsError):claim_once(p/'claims','b'*64,p/'one',{})
    def test_limit_rejection_and_no_learning_import(self):
        from run_preflight import check_limits,NoLearning,require_registered_location
        require_registered_location()
        check_limits(kind='dynamic',cycles=14499,steps=144990,elapsed=1199,whole=21599,static_elapsed=0)
        for key,val in [('cycles',14500),('steps',145000),('elapsed',1200),('whole',21600)]:
            kw=dict(kind='dynamic',cycles=0,steps=0,elapsed=0,whole=0,static_elapsed=0);kw[key]=val
            with self.assertRaises(TimeoutError):check_limits(**kw)
        with self.assertRaises(ValueError):check_limits(kind='static',cycles=0,steps=0,elapsed=0,whole=0,static_elapsed=0)
        for name in ('torch','stable_baselines3.sac','jax'):
            with self.assertRaises(ImportError):NoLearning().find_spec(name)

if __name__=='__main__':unittest.main(verbosity=2)
