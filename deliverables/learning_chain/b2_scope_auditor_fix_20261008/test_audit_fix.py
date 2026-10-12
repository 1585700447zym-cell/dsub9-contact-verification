"""Regression tests against real numerical types and the preserved P01 archive.

The --auditor switch runs identical expectations against the broken or fixed
implementation. No simulator or learning library may be imported.
"""
import argparse
from copy import deepcopy
import importlib.abc
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(r'D:\dsub9项目计划\first_stage_sim\.worktrees\dsub9-v1-contact-validation')
OUT = Path(__file__).resolve().parent
SOURCE = ROOT / 'deliverables/learning_chain/b2_pose_scope_preflight_20261008'
RUN = ROOT / 'deliverables/learning_chain/b2_pose_scope_execution_20261008/run'
FORBIDDEN = {'mujoco', 'torch', 'stable_baselines3', 'tensorflow', 'jax', 'gymnasium'}

class OfflineOnly(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in FORBIDDEN:
            raise ImportError('Offline regression prohibits ' + fullname)

sys.meta_path.insert(0, OfflineOnly())
parser = argparse.ArgumentParser()
parser.add_argument('--auditor', type=Path, required=True)
args, rest = parser.parse_known_args()
sys.path.insert(0, str(SOURCE))
spec = importlib.util.spec_from_file_location('repaired_assess', args.auditor.resolve())
api = importlib.util.module_from_spec(spec)
sys.modules['repaired_assess'] = api
spec.loader.exec_module(api)
import numpy as np

class ScalarTests(unittest.TestCase):
    def accepted(self, left, right, tolerance=1e-12):
        try:
            api.same(left, right, 'regression', tolerance)
        except (ValueError, TypeError) as exc:
            self.fail('Equal supported values were rejected: ' + repr(exc))

    # Catches the actual live reward failure and the opposite JSON reload case.
    def test_equal_finite_numbers_in_both_representations(self):
        for dtype in (np.float16, np.float32, np.float64, np.int32, np.int64, np.uint64):
            for left, right in ((dtype(1), 1), (1, dtype(1))):
                with self.subTest(dtype=str(dtype), side=type(left).__name__):
                    self.accepted(left, right)

    def test_nested_command_and_reward_json_roundtrip(self):
        live = {'command': [np.float64(0), np.float64(.001)],
                'reward': {'progress': np.float64(2.37286798391613e-06)}, 'active': True}
        saved = {'command': [0., .001], 'reward': {'progress': 2.37286798391613e-06}, 'active': True}
        self.accepted(live, saved)
        self.accepted(saved, live)

    def test_same_boolean_values_keep_boolean_semantics(self):
        self.accepted(np.bool_(True), True)
        self.accepted(False, np.bool_(False))

    # Catches blanket float conversion, truth coercion or relaxed tolerance.
    def test_large_integer_low_bits_are_not_discarded(self):
        self.accepted(np.uint64(2**63 + 1), 2**63 + 1)
        for a, b in ((np.uint64(2**63 + 1), 2**63), (2**63, np.uint64(2**63 + 1))):
            with self.assertRaises(ValueError):
                api.same(a, b, 'low bit')

    def test_existing_tolerance_is_preserved(self):
        self.accepted(np.float64(1 + 5e-13), 1.)
        with self.assertRaises(ValueError):
            api.same(np.float64(1 + 2e-12), 1., 'difference')

    def test_large_integer_float_comparison_keeps_exact_difference(self):
        for a, b in ((np.uint64(2**63 + 1), float(2**63)),
                     (2**53 + 1, np.float64(2**53))):
            for left, right in ((a, b), (b, a)):
                with self.subTest(left=repr(left)), self.assertRaises(ValueError):
                    api.same(left, right, 'mixed low bit')
        self.accepted(np.uint64(2**63), float(2**63))

    def test_nonfinite_values_are_rejected_even_same_type(self):
        for value in (float('nan'), float('inf'), -float('inf')):
            for a, b in ((value, np.float64(value)), (np.float64(value), value), (np.float64(value), np.float64(value))):
                with self.subTest(value=value, a=type(a).__name__), self.assertRaises(ValueError):
                    api.same(a, b, 'nonfinite')

    def test_boolean_number_mixing_is_rejected(self):
        for a, b in ((True, 1.), (np.bool_(True), 1), (1, np.bool_(True)), (np.float64(1), True)):
            with self.subTest(a=repr(a), b=repr(b)), self.assertRaises(ValueError):
                api.same(a, b, 'boolean schema')

    def test_non_numeric_coercions_and_arrays_are_rejected(self):
        for value in ('1', None, [1], np.array(1.), complex(1), np.complex128(1)):
            for a, b in ((value, 1.), (1., value)):
                with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                    api.same(a, b, 'unsupported type')

    def test_keys_shapes_and_text_remain_strict(self):
        for a, b in (({'a': 1}, {'b': 1}), ([1, 2], [1]), ('RUNNING', 'STOPPING'), (None, False)):
            with self.subTest(a=a), self.assertRaises(ValueError):
                api.same(a, b, 'structure')

class ArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from scope_contract import sha
        from run_preflight import check_binding, BINDING
        _, b = check_binding()
        cls.binding = dict(b, binding_sha256=sha(BINDING))
        cls.raw = api.read_archive(RUN / 'P01_zero.json.gz')

    def verified(self, raw):
        try:
            result = api.assess_raw(raw, raw['spec'], self.binding)
        except ValueError as exc:
            self.fail('Preserved valid physical evidence was rejected: ' + repr(exc))
        self.assertTrue(result['audit_passed'])
        self.assertTrue(result['functional_success'])
        self.assertTrue(result['strict_precision_success'])
        self.assertAlmostEqual(result['failure_penalized_task_time_s'], 4.330, places=9)
        self.assertEqual(result['observation']['vectors_verified'], 3046)
        self.assertEqual(result['contact_cycles'], 0)
        self.assertFalse(result['training_admitted'])

    def test_real_serialized_archive_passes_complete_audit(self):
        self.verified(self.raw)

    def test_real_values_restored_to_live_numpy_reward_and_command_types(self):
        # Archived numbers, unchanged; restore only the scalar types produced by
        # reward/session and command composition, without invoking the engine.
        raw = deepcopy(self.raw)
        for cycle in raw['cycles']:
            result = cycle['result']
            for name in ('progress', 'total'):
                result['reward_terms'][name] = np.float64(result['reward_terms'][name])
            key = 'unfiltered_stage_limited_total'
            result['action_log'][key] = [np.float64(v) for v in result['action_log'][key]]
        self.verified(raw)

    def test_real_reward_corruption_is_still_rejected(self):
        raw = deepcopy(self.raw)
        raw['cycles'][0]['result']['reward_terms']['progress'] += .0001
        with self.assertRaisesRegex(ValueError, r'reward\.progress'):
            api.assess_raw(raw, raw['spec'], self.binding)

    def test_closed_attempt_is_not_promoted_by_repair(self):
        result = api.assess(RUN)
        self.assertEqual(result['route'], 'NO_SCOPE_QUALIFICATION')
        self.assertEqual(result['dynamic'][0]['status'], 'error')
        self.assertEqual(sum(r['status'] == 'NOT_ATTEMPTED' for r in result['dynamic']), 15)
        self.assertFalse(result['new_training_authorized'])

if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]] + rest, verbosity=2)
