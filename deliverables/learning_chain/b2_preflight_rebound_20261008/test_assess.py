"""Synthetic archive mutation tests; these are not physical evidence."""
from copy import deepcopy
from pathlib import Path
import unittest
from test_scope_preflight import module, temporary_directory


class AssessmentTests(unittest.TestCase):
    def setUp(self):
        self.api=module('assess')
        self.assertIsNotNone(self.api,'Missing read-only archive assessor')

    def test_success_and_failure_keep_separate_metrics(self):
        for success in (True,False):
            from synthetic_fixtures import fixture
            raw=fixture(success=success)
            result=self.api.assess_raw(raw,raw['spec'],{'binding_sha256':'fixture'})
            self.assertTrue(result['audit_passed'])
            self.assertEqual(result['functional_success'],success)
            self.assertEqual(result['failure_penalized_task_time_s'],.2 if success else 26.)
            self.assertEqual(result['recovery_coverage'],'INSUFFICIENT_COVERAGE')
            self.assertEqual(result['effect_coverage'],'INSUFFICIENT_COVERAGE')

    def test_missing_context_and_bad_reward_command_or_stop_rejected(self):
        from synthetic_fixtures import fixture
        source=fixture(success=False)
        for field in ('before','composition','reward','stop','angle','count','geometry'):
            raw=deepcopy(source)
            if field=='before':del raw['cycles'][0]['before']
            elif field=='composition':raw['cycles'][0]['composition']=[]
            elif field=='reward':raw['cycles'][0]['result']['reward_terms']['total']+=1
            elif field=='stop':raw['stop_samples']=[]
            elif field=='angle':raw['initial']['quaternion_wxyz']=[1.,0.,0.,0.]
            elif field=='count':raw['physical_substeps']=145001
            else:
                raw['final_session']['reason']='GEOMETRIC_SUCCESS';raw['outcome']['task_outcome']='FULL_SUCCESS'
            with self.subTest(field=field),self.assertRaises((ValueError,KeyError)):
                self.api.assess_raw(raw,raw['spec'],{'binding_sha256':'fixture'})

    def test_partial_and_missing_attempts_remain_in_denominator(self):
        with temporary_directory() as t:
            from execution_contract import write
            write(Path(t)/'ledger.json',dict(status='CLOSED_ERROR',attempts=[
                dict(id='init_zero_sentinel',kind='static',status='error')]))
            result=self.api.assess(Path(t),verify_binding=False)
            self.assertEqual(len(result['static']),9)
            self.assertEqual(len(result['dynamic']),16)
            self.assertEqual(result['dynamic'][0]['status'],'NOT_ATTEMPTED')
            self.assertIsNone(result['dynamic'][0]['functional_success'])
            self.assertEqual(result['route'],'NO_SCOPE_QUALIFICATION')


if __name__=='__main__':unittest.main(verbosity=2)
