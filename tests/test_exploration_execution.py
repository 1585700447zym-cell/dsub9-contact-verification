"""Checks for the diagnostic itself; no physics or learning is run here."""
import unittest
import json
import tempfile
from pathlib import Path
import numpy as np
from tools.learning.exploration_execution import HeldRequests, command_metrics


class ExecutionDiagnosticTests(unittest.TestCase):
    def test_hold_interrupts_on_phase_permission_gap_and_reset(self):
        stream = np.array([[.1]*5, [.2]*5, [.3]*5, [.4]*5])
        held = HeldRequests(stream, hold_cycles=10)
        for cycle in range(10):
            np.testing.assert_array_equal(held.select(cycle, 'SEARCH'), [.1]*5)
        np.testing.assert_array_equal(held.select(10, 'SEARCH'), [.2]*5)
        np.testing.assert_array_equal(held.select(11, 'INSERT'), [.3]*5)
        np.testing.assert_array_equal(held.select(14, 'INSERT'), [.4]*5)
        held.reset()
        np.testing.assert_array_equal(held.select(0, 'SEARCH'), [.1]*5)

    def test_two_ms_draws_every_enabled_cycle(self):
        held = HeldRequests(np.array([[.1]*5, [-.1]*5]), hold_cycles=1)
        np.testing.assert_array_equal(held.select(0, 'INSERT'), [.1]*5)
        np.testing.assert_array_equal(held.select(1, 'INSERT'), [-.1]*5)

    @staticmethod
    def steady_rows(sign=1., filtered=False):
        # Already tracking 50 um/s. The zero shadow needs five ticks to stop.
        rows = []
        for i in range(10):
            rows.append(dict(action_active=True, dt=.002, action=[sign, 0, 0, 0, 0],
                action_log=dict(composition_inputs=dict(base_command=[0.]*6,
                    previous_limited_command=[sign*.00005, 0, 0, 0, 0, 0], phase='INSERT', dt=.002),
                    actual_end_limited_command=[sign*.00005, 0, 0, 0, 0, 0],
                    applied_residual=[sign*.00005, 0, 0, 0, 0, 0],
                    effective_command_delta=[sign*.00001, 0, 0, 0, 0, 0],
                    reference_filter_fraction=.5 if filtered and i == 4 else 1.)))
        return rows

    def test_shadow_uses_own_previous_command_in_both_directions(self):
        for sign in (1., -1.):
            metrics = command_metrics(self.steady_rows(sign))['all']
            self.assertAlmostEqual(metrics['gain'][0], .8)
            self.assertAlmostEqual(metrics['tracking_error'][0], 0.)
            self.assertAlmostEqual(metrics['local_gain_auxiliary'][0], .2)
            self.assertIsNone(metrics['gain'][1])  # No invented epsilon denominator.

    def test_reference_filter_prevents_a_false_gate_pass(self):
        metrics = command_metrics(self.steady_rows(filtered=True))
        self.assertFalse(metrics['gain_admissible'])

    def test_shadow_resets_at_phase_boundary(self):
        rows = self.steady_rows()[:5] + self.steady_rows()[:5]
        for row in rows[5:]:
            row['action_log']['composition_inputs']['phase'] = 'SEARCH'
            row['action_log'].update(reference_xy_m=[0., 0.], reference_radius_limit_m=.0004)
        self.assertAlmostEqual(command_metrics(rows)['all']['gain'][0], .6)

    def test_interrupted_batch_reconciles_completed_and_inflight_costs(self):
        from tools.validation.run_exploration_execution import reconcile_batch
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, receipt, progress in [
                ('A', dict(status='finished', reset_attempted=1, physical_substeps=135000,
                           control_cycles=13500), {}),
                ('B', dict(status='initializing', reset_attempted=1, physical_substeps=0),
                      dict(cycles=300, physical_substeps=3000, reset_attempted=1))]:
                folder = root / name; folder.mkdir()
                (folder / 'receipt.json').write_text(json.dumps(receipt), encoding='utf-8')
                (folder / 'progress.json').write_text(json.dumps(progress), encoding='utf-8')
            ledger = dict(episodes=[], initialization_attempts=0, physical_substeps=0)
            reconcile_batch(ledger, [dict(id='A'), dict(id='B')], root)
            self.assertEqual(ledger['initialization_attempts'], 2)
            self.assertEqual(ledger['physical_substeps'], 138000)
            self.assertEqual(len(ledger['episodes']), 2)
            self.assertEqual(ledger['episodes'][1]['count_precision'], 'lower_bound')


if __name__ == '__main__':
    unittest.main()
