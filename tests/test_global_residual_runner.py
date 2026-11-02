"""Pure registration, script, admission and interrupted-cost checks; no physics."""
import importlib
import json
from pathlib import Path
import tempfile
import unittest


def runner():
    try:
        return importlib.import_module('tools.validation.run_global_residual_authority')
    except ModuleNotFoundError:
        raise AssertionError('Independent global residual runner has not been implemented')


class GlobalResidualRunnerTests(unittest.TestCase):
    def test_script_waits_for_first_search_then_starts_at_point_two_seconds(self):
        script = runner().DiagnosticScript()
        for cycle in range(30):
            self.assertEqual(script.select(cycle, 'INSERT', True), [0.] * 5)
        for cycle in range(30, 131):
            self.assertEqual(script.select(cycle, 'SEARCH', True), [0.] * 5)
        self.assertAlmostEqual(script.select(131, 'SEARCH', True)[4], .01)

    def test_six_trapezoids_have_registered_order_duration_and_integrals(self):
        script = runner().DiagnosticScript()
        values = [script.select(cycle, 'SEARCH', True) for cycle in range(3700)]
        for start, axis, sign in [(100, 4, 1.), (700, 4, -1.),
                                  (1300, 0, 1.), (1900, 0, -1.),
                                  (2500, 1, 1.), (3100, 1, -1.)]:
            self.assertEqual(values[start], [0.] * 5)
            self.assertAlmostEqual(values[start + 50][axis], sign * .5)
            self.assertAlmostEqual(values[start + 100][axis], sign)
            self.assertAlmostEqual(values[start + 399][axis], sign)
            self.assertAlmostEqual(values[start + 450][axis], sign * .5)
            self.assertAlmostEqual(sum(v[axis] for v in values[start:start + 500]) * .002, sign * .8)
            self.assertTrue(all(v == [0.] * 5 for v in values[start + 500:start + 600]))
        self.assertEqual(script.state()['status'], 'completed')

    def test_phase_exit_cancels_remaining_pulses_even_during_initial_wait(self):
        script = runner().DiagnosticScript()
        script.select(0, 'SEARCH', True)
        self.assertEqual(script.select(1, 'INSERT', True), [0.] * 5)
        self.assertEqual(script.select(200, 'SEARCH', True), [0.] * 5)
        self.assertEqual(script.state()['cancellation_reason'], 'SEARCH_EXIT')

    def test_permission_gap_is_observed_and_cannot_resume_the_script(self):
        script = runner().DiagnosticScript()
        script.select(0, 'SEARCH', True)
        self.assertAlmostEqual(script.select(150, 'SEARCH', True)[4], .5)
        self.assertEqual(script.select(151, 'SEARCH', False), [0.] * 5)
        self.assertEqual(script.select(152, 'SEARCH', True), [0.] * 5)
        self.assertEqual(script.state()['cancellation_reason'], 'RESIDUAL_PERMISSION_INTERRUPTED')

    def test_first_search_without_permission_consumes_the_only_script_opportunity(self):
        script = runner().DiagnosticScript()
        script.select(0, 'SEARCH', False)
        self.assertEqual(script.select(150, 'SEARCH', True), [0.] * 5)
        self.assertEqual(script.state()['status'], 'cancelled')

    def test_script_repeated_snapshot_does_not_restart_or_advance(self):
        script = runner().DiagnosticScript()
        script.select(0, 'SEARCH', True)
        self.assertEqual(script.select(150, 'SEARCH', True), script.select(150, 'SEARCH', True))
        with self.assertRaises(ValueError):
            script.select(149, 'SEARCH', True)

    def test_schedule_pairs_same_pose_before_changing_yaw(self):
        jobs = runner().schedule()
        self.assertEqual([job['id'] for job in jobs], ['G0_YAW_P15', 'G1_YAW_P15', 'G0_YAW_M15', 'G1_YAW_M15'])
        self.assertEqual(jobs[0]['case'], jobs[1]['case'])
        self.assertEqual(jobs[2]['case'], jobs[3]['case'])
        self.assertGreater(jobs[0]['case']['yaw_rad'], 0.)
        self.assertLess(jobs[2]['case']['yaw_rad'], 0.)

    def test_pair_two_is_never_launched_after_pair_one_audit_fails(self):
        launched = []
        def launch(job):
            launched.append(job['id'])
            return job['id']
        def audit_pair(pair):
            raise ValueError('Saved archive is invalid')
        with self.assertRaises(ValueError):
            runner().execute_pairs(runner().schedule(), launch, audit_pair)
        self.assertCountEqual(launched, ['G0_YAW_P15', 'G1_YAW_P15'])

    def test_valid_task_protection_failure_can_pass_batch_gate(self):
        receipt = dict(status='finished', valid=True, stopped=True,
            process_exit_confirmed=True, returncode=0, reset_attempted=1,
            physical_substeps=2000, control_cycles=200, nonfinite_fields=[],
            guard_facts=dict(simulation_valid=True, invalid_reasons=[], motion_reasons=[], contact_reasons=['FORCE_LIMIT']),
            outcome='CONTACT_GUARD', archive_sha256='saved')
        audit = dict(verified=True, script_verified=True, archive_sha256='saved')
        self.assertTrue(runner().continue_batch(receipt, audit))
        receipt['guard_facts']['motion_reasons'] = ['TRAVEL_LIMIT']
        self.assertFalse(runner().continue_batch(receipt, audit))

    def test_inexact_or_mismatched_counters_stop_batch(self):
        base = dict(status='finished', valid=True, stopped=True,
            process_exit_confirmed=True, returncode=0, reset_attempted=1,
            physical_substeps=2000, control_cycles=200, nonfinite_fields=[],
            guard_facts=dict(simulation_valid=True, invalid_reasons=[], motion_reasons=[]), archive_sha256='saved')
        audit = dict(verified=True, script_verified=True, archive_sha256='saved')
        for delta in [dict(count_precision='lower_bound'), dict(physical_substeps=2001),
                      dict(control_cycles=16001), dict(reset_attempted=0), dict(returncode=1)]:
            self.assertFalse(runner().continue_batch(dict(base, **delta), audit))

    def test_partial_reconciliation_uses_thirty_two_second_bound_and_unknown_initialization(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'G0_YAW_P15'; folder.mkdir()
            (folder / 'worker.claim').write_text('started', encoding='utf-8')
            (folder / 'progress.json').write_text(json.dumps(dict(cycles=12, physical_substeps=120, reset_attempted=1)), encoding='utf-8')
            ledger = {}
            failures = runner().reconcile_batch(ledger, runner().schedule(), Path(tmp))
            self.assertEqual(failures, ['G0_YAW_P15'])
            self.assertEqual(ledger['physical_substeps'], 120)
            self.assertEqual(ledger['initialization_attempts'], 1)
            self.assertEqual(ledger['episodes'][0]['physical_substeps_upper_bound'], 160000)
            self.assertEqual(ledger['count_precision'], 'lower_bound')
            self.assertEqual(ledger['cumulative_initializations_lower_bound'], 416)

    def test_claimed_worker_without_progress_is_preserved_as_unknown_cost(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'G0_YAW_P15'; folder.mkdir()
            (folder / 'worker.claim').write_text('started', encoding='utf-8')
            ledger = {}
            runner().reconcile_batch(ledger, runner().schedule(), Path(tmp))
            self.assertEqual(ledger['unknown_initialization_attempts_upper_bound'], 1)
            self.assertEqual(ledger['physical_substeps_upper_bound'], 160000)
            self.assertEqual(ledger['cumulative_initializations_upper_bound'], 416)

    def test_import_does_not_load_physics_or_neural_packages(self):
        import subprocess
        import sys
        result = subprocess.run([sys.executable, '-B', '-c',
            "import sys; import tools.validation.run_global_residual_authority; "
            "assert not any(n.split('.')[0] in ('mujoco','torch','stable_baselines3') for n in sys.modules)"],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_task_clock_accepts_legacy_settle_inside_independent_stop_tail(self):
        self.assertTrue(hasattr(runner(), 'verify_task_clock'), '30-second task clock checker is missing')
        runner().verify_task_clock(stop_time=30., task_end_time=31., audit_end_time=32., settle_time=1.)
        for delta in [dict(stop_time=30.002), dict(task_end_time=31.002), dict(audit_end_time=32.002)]:
            args = dict(stop_time=30., task_end_time=31., audit_end_time=32., settle_time=1.)
            args.update(delta)
            with self.assertRaises(ValueError):
                runner().verify_task_clock(**args)

    def test_source_inventory_covers_dynamic_auditor_and_loaded_mesh_assets(self):
        self.assertTrue(hasattr(runner(), 'implementation_sources'), 'Actual source inventory is missing')
        paths = {path.relative_to(runner().ROOT).as_posix() for path in runner().implementation_sources()}
        self.assertIn('deliverables/learning_chain/b2_newton_sac_preparation_20261016/newton_raw_audit.py', paths)
        self.assertIn('deliverables/b2_search_recovery/matrix_v1_7cases/results_index.json', paths)
        self.assertIn('assets/visual/dsub9_male_visual_centered.stl', paths)
        self.assertIn('assets/collision/d_guide_male_seg_000.stl', paths)

    def test_composition_audit_rejects_reference_and_filter_attribution_tampering(self):
        from copy import deepcopy
        from tools.learning.global_residual_action import compose_command
        from tools.learning.five_axis_contract import field_slices
        self.assertTrue(hasattr(runner(), 'verify_composition_log'), 'Independent composition log check is missing')
        _, expected = compose_command([0.] * 6, [0., 0., 0., 0., 1.], profile='G1',
            phase='SEARCH', enabled=True, previous_limited=[0.] * 6, dt=.002, reference_xy=[0., 0.])
        observation = [0.] * 140
        spans = field_slices()
        for name in ('base_command', 'previous_limited_command', 'search_reference_xy_m'):
            observation[spans[name]] = [0.] * (spans[name].stop - spans[name].start)
        cfg = dict(spiral_radius_m=.0004)
        runner().verify_composition_log(expected, expected, observation, cfg)
        for field, value in [('reference_xy_m', [.0001, 0.]), ('reference_radius_limit_m', .0005),
                             ('reference_filter_fraction', .5), ('pre_stage_total', [0.] * 6),
                             ('stage_clip_delta', [1.] * 6), ('drive_clip_delta', [1.] * 6)]:
            changed = deepcopy(expected); changed[field] = value
            with self.assertRaises(ValueError, msg=field):
                runner().verify_composition_log(changed, expected, observation, cfg)


if __name__ == '__main__':
    unittest.main()
