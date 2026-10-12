"""Pure reproductions of final-review failure paths; no model or process launch."""
import gzip
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT))
import scope_contract as c
import baseline_entry as entry
import assess_results as a


class ReviewRegressions(unittest.TestCase):
    def api(self,module,name):
        self.assertTrue(callable(getattr(module,name,None)),'Missing reviewed behavior: '+name)
        return getattr(module,name)

    def test_outer_kill_reconciles_late_receipt_and_marks_unobserved_control_tail(self):
        fn=self.api(entry,'reconcile_attempts')
        with tempfile.TemporaryDirectory(dir=OUT) as td:
            root=Path(td);run=root/'case_0';run.mkdir()
            ledger=dict(episodes=[dict(case_id='D00',status='claimed',healthy=False)])
            c.write(run/'receipt.json',dict(case_id='D00',status='running',healthy=False,
                environment_creation_attempted=1,environment_created=1,reset_attempted=1,reset_completed=1,
                control_cycles=500,physical_substeps=5000))
            fn(ledger,root,dict(process_exit_confirmed=True,owned_launcher_exit_confirmed=True))
            row=ledger['episodes'][0]
            self.assertEqual(row['reset_attempted'],1);self.assertEqual(row['control_cycles'],500)
            self.assertEqual(row['control_count_evidence'],'lower_bound');self.assertTrue(row['package_tree_exit_confirmed'])
            self.assertFalse(row['receipt_costs_complete']);self.assertFalse(row['healthy'])

    def test_pre_go_reservation_never_increments_actual_dynamic_total(self):
        fn=self.api(a,'cost_summary')
        row=dict(case_id='D00',status='claimed',healthy=False,operation_counts_known=True,
            environment_creation_attempted=0,environment_created=0,reset_attempted=0,reset_completed=0,
            control_cycles=0,physical_substeps=0,receipt_costs_complete=True)
        costs=fn([row]);self.assertEqual(costs['claimed_slots'],1);self.assertEqual(costs['reset_attempts'],0)
        self.assertEqual(costs['cumulative_dynamic'],258);self.assertEqual(costs['native_steps_recorded'],0)

    def test_missing_receipt_and_unknown_go_do_not_become_zero_measurement(self):
        reconcile=self.api(entry,'reconcile_attempts');costs=self.api(a,'cost_summary')
        with tempfile.TemporaryDirectory(dir=OUT) as td:
            ledger=dict(episodes=[dict(case_id='D00',status='claimed',healthy=False)])
            reconcile(ledger,Path(td),dict(process_exit_confirmed=True))
            out=costs(ledger['episodes'])
            self.assertEqual(out['unknown_operation_attempts'],1);self.assertIsNone(out['cumulative_dynamic'])
            self.assertEqual(out['cumulative_dynamic_range'],[258,259])

    def test_finished_archive_with_failed_exit_is_retained_as_fault_without_statistics(self):
        fn=self.api(a,'assess_entry')
        with tempfile.TemporaryDirectory(dir=OUT) as td:
            path=Path(td)/'episode.json.gz';path.write_bytes(gzip.compress(json.dumps(dict(attempt_index=0)).encode()))
            reservation=dict(case_id='D00',status='finished',healthy=True,archive_sha256=c.sha(path),
                supervisor=dict(go_issued=True,process_exit_confirmed=False,owned_launcher_exit_confirmed=True,returncode=1))
            saved=dict(case_id='D00',task_outcome='FULL_SUCCESS',simulation_valid=True,physical_stopped=True,guard=False,task_time_s=10.)
            with patch.object(a,'record',return_value=saved):
                row,fault=fn(reservation,path,c.read(OUT/'configuration.json'),0)
            self.assertIsNone(row);self.assertEqual(fault['reason'],'supervision_or_receipt_incomplete')
            self.assertEqual(fault['archived_summary'],saved);self.assertTrue(path.exists())

    def test_corrupt_archive_is_retained_and_does_not_abort_all_attempts(self):
        fn=self.api(a,'assess_entry')
        with tempfile.TemporaryDirectory(dir=OUT) as td:
            path=Path(td)/'episode.json.gz';path.write_bytes(b'not-gzip')
            reservation=dict(case_id='D00',status='finished',healthy=False,archive_sha256=c.sha(path))
            row,fault=fn(reservation,path,c.read(OUT/'configuration.json'),0)
            self.assertIsNone(row);self.assertEqual(fault['reason'],'archive_audit_failed');self.assertTrue(path.exists())

    def test_planned_success_quantiles_use_fixed_linear_interpolation(self):
        rows=[dict(case_id=case,task_outcome='FULL_SUCCESS',simulation_valid=True,physical_stopped=True,guard=False,task_time_s=t)
              for case,t in [('D00',1.),('P1',5.),('P2',9.)]]
        out=a.summarize(rows,['D00','P1','P2'])
        self.assertIn('success_p50_s',out,'Missing planned quantiles')
        self.assertEqual(out['success_p50_s'],5.);self.assertAlmostEqual(out['success_p90_s'],8.2)


if __name__=='__main__':unittest.main(verbosity=2)
