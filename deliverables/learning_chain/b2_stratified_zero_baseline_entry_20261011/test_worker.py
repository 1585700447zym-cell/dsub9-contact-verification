"""Real reset/receipt and audit boundary behavior with no native simulation."""
import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT))
import scope_contract as c
import baseline_rollout as worker


class WorkerTests(unittest.TestCase):
    def api(self,name):
        self.assertTrue(callable(getattr(worker,name,None)),'Missing behavior: '+name)
        return getattr(worker,name)

    def config(self):return c.read(OUT/'configuration.json')

    def session(self,bad=False):
        config=self.config();row=dict(position_m=[0.,0.,-.004],quaternion_wxyz=[1.,0.,0.,0.],
            contact_count=int(bad),penetration_m=0.,velocity_world=[0.]*6,contact_wrench_M=[0.]*6,contact_wrench_G=[0.]*6)
        facts=dict(simulation_valid=True,invalid_reasons=[],contact_reasons=[],motion_reasons=[])
        s=SimpleNamespace(initial_trace_row=row,env=SimpleNamespace(guard_facts=facts),calls=0)
        def reset(case,seed):
            s.calls+=1;return 'snapshot'
        s.reset=reset
        return s

    def test_reset_is_charged_before_call_and_usable_only_once(self):
        fn=self.api('reset_once')
        with tempfile.TemporaryDirectory(dir=OUT) as td:
            run=Path(td);receipt=dict(reset_attempted=0,reset_completed=0);s=self.session()
            original=s.reset
            def reset(case,seed):
                self.assertEqual(c.read(run/'receipt.json')['reset_attempted'],1)
                return original(case,seed)
            s.reset=reset
            self.assertEqual(fn(s,object(),c.new_cases()[0],receipt,run,self.config()),'snapshot')
            self.assertTrue(c.read(run/'receipt.json')['initial_audit']['passed'])
            with self.assertRaises(ValueError):fn(s,object(),c.new_cases()[0],receipt,run,self.config())
            self.assertEqual(s.calls,1)

    def test_initial_contact_failure_retains_charged_successful_reset(self):
        fn=self.api('reset_once')
        with tempfile.TemporaryDirectory(dir=OUT) as td:
            run=Path(td);receipt=dict(reset_attempted=0,reset_completed=0);s=self.session(True)
            with self.assertRaises(ValueError):fn(s,object(),c.new_cases()[0],receipt,run,self.config())
            saved=c.read(run/'receipt.json');self.assertEqual(saved['reset_attempted'],1);self.assertEqual(saved['reset_completed'],1)
            self.assertNotIn('initial_audit',saved);self.assertEqual(s.calls,1)

    def test_reset_exception_retains_attempt_without_fabricated_completion(self):
        fn=self.api('reset_once')
        with tempfile.TemporaryDirectory(dir=OUT) as td:
            run=Path(td);receipt=dict(reset_attempted=0,reset_completed=0);s=self.session()
            def fail(*a,**k):raise RuntimeError('native reset fixture failure')
            s.reset=fail
            with self.assertRaises(RuntimeError):fn(s,object(),c.new_cases()[0],receipt,run,self.config())
            self.assertEqual(c.read(run/'receipt.json'),dict(reset_attempted=1,reset_completed=0))

    def raw(self):
        point=c.new_cases()[0];config=self.config()
        return dict(case=point,case_id='D00',case_index=0,attempt_index=0,
            simulation_case=c.case_kwargs(point),comparison_key=config['common_key'],role='pure_B2',
            policy_calls=0,optimizer_steps=0,optimizer_steps_start=0,policy_sha256=None,fault=None,
            reference_problems=[],actual_reference_failed=False,control_cycles=1,physical_substeps=10,
            initial_audit=dict(passed=True),source_session_outcome=dict(simulation_valid=True,physical_stopped=True,
                model_scope_qualified=False,training_admitted=False),
            outcome=dict(simulation_valid=True,physical_stopped=True,guard_violations=dict(contact=False,motion=False),task_outcome='FULL_SUCCESS'),
            trace=[dict(position_m=[0.,0.,-.004],quaternion_wxyz=[1.,0.,0.,0.]),{}],
            actions=[dict(raw_action=[0.]*4,experience_action=[0.]*4,requested_residual=[0.]*6,applied_residual=[0.]*6,effective_command_delta=[0.]*6)],transitions=[{}])

    def test_zero_archive_identity_and_original_negative_qualification_preserved(self):
        fn=self.api('audit_baseline');self.assertTrue(fn(self.raw(),self.config()))
        raw=self.raw();raw['source_session_outcome']['training_admitted']=True
        with self.assertRaises(ValueError):fn(raw,self.config())

    def test_nonzero_action_and_wrong_matrix_scope_rejected(self):
        fn=self.api('audit_baseline')
        raw=self.raw();raw['actions'][0]['raw_action'][1]=1e-12
        with self.assertRaises(ValueError):fn(raw,self.config())
        raw=self.raw();raw['comparison_key']=self.config()['legacy_four_point_comparison_key']
        with self.assertRaises(ValueError):fn(raw,self.config())

    def test_bad_length_substeps_and_initial_audit_cannot_be_healthy(self):
        fn=self.api('audit_baseline')
        for key,value in [('physical_substeps',11),('initial_audit',dict(passed=False)),('transitions',[])]:
            raw=self.raw();raw[key]=value
            with self.assertRaises(ValueError):fn(raw,self.config())

    def test_valid_ordinary_failure_and_guard_are_distinct(self):
        fn=self.api('audit_baseline');raw=self.raw();raw['outcome']['task_outcome']='TASK_FAILURE'
        self.assertTrue(fn(raw,self.config()))
        raw['outcome']['guard_violations']['contact']=True;raw['outcome']['task_outcome']='CONTACT_GUARD'
        self.assertFalse(fn(raw,self.config()))


if __name__=='__main__':unittest.main(verbosity=2)
