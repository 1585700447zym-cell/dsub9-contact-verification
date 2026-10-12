"""Failure accounting, matrix completeness, aliases and geometric evidence."""
import copy
from pathlib import Path
import sys
import unittest

OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT))
import scope_contract as c
import assess_results as a
import baseline_rollout as w


class AssessmentTests(unittest.TestCase):
    def api(self,name):
        self.assertTrue(callable(getattr(a,name,None)),'Missing behavior: '+name)
        return getattr(a,name)

    def records(self):
        return [dict(case_id=p['id'],task_outcome='FULL_SUCCESS',simulation_valid=True,
            physical_stopped=True,guard=False,task_time_s=10.) for p in c.registered_cases()]

    def test_complete25_mean_and_valid_failure_penalty(self):
        fn=self.api('summarize');rows=self.records();rows[0]['task_outcome']='TASK_FAILURE'
        out=fn(rows,[p['id'] for p in c.registered_cases()])
        self.assertEqual(out['functional_successes'],24);self.assertAlmostEqual(out['mean_penalized_time_s'],10.64)
        self.assertEqual(out['ordinary_failures'],1);self.assertEqual(out['expected'],25)

    def test_missing_invalid_unstopped_and_guard_never_make_complete_mean(self):
        fn=self.api('summarize');ids=[p['id'] for p in c.registered_cases()]
        self.assertIsNone(fn(self.records()[:-1],ids)['mean_penalized_time_s'])
        for key,value in [('simulation_valid',False),('physical_stopped',False),('guard',True)]:
            rows=self.records();rows[0][key]=value
            self.assertIsNone(fn(rows,ids)['mean_penalized_time_s'])

    def test_duplicate_unknown_cases_and_nan_time_rejected(self):
        fn=self.api('summarize');ids=[p['id'] for p in c.registered_cases()]
        with self.assertRaises(ValueError):fn(self.records()+[self.records()[0]],ids)
        rows=self.records();rows[0]['case_id']='J01'
        with self.assertRaises(ValueError):fn(rows,ids)
        rows=self.records();rows[0]['task_time_s']=float('nan')
        with self.assertRaises(ValueError):fn(rows,ids)

    def test_guard_does_not_receive_ordinary26s_penalty(self):
        fn=self.api('summarize');rows=self.records();rows[0].update(guard=True,task_outcome='CONTACT_GUARD')
        out=fn(rows,[p['id'] for p in c.registered_cases()]);self.assertEqual(out['ordinary_failures'],0)
        self.assertEqual(out['guards'],1);self.assertIsNone(out['mean_penalized_time_s'])

    def test_old_four_aliases_preserve_original_case_and_fingerprint(self):
        fn=self.api('reused_records');rows=fn()
        self.assertEqual([r['case_id'] for r in rows],['J11','J22','J33','J44'])
        self.assertEqual([r['original_case_id'] for r in rows],['J01','J02','J03','J04'])
        self.assertTrue(all(r['original_comparison_key'].startswith('d06ace') and r['reused'] for r in rows))

    def test_unfinished_ledger_refuses_result_assessment(self):
        fn=self.api('require_closed')
        with self.assertRaises(ValueError):fn(dict(status='RUNNING',episodes=[]),dict(status='RUNNING'))

    def test_clearance_negative_infinity_retains_no_overlap_status(self):
        self.assertTrue(callable(getattr(w,'serialize_clearance',None)),'Missing clearance serialization')
        self.assertEqual(w.serialize_clearance(float('-inf')),dict(value_m=None,status='no_main_overlap'))
        self.assertEqual(w.serialize_clearance(-1e-9),dict(value_m=-1e-9,status='finite'))
        with self.assertRaises(ValueError):w.serialize_clearance(float('nan'))


if __name__=='__main__':unittest.main(verbosity=2)
