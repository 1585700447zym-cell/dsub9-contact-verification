"""Standard-library contract tests. No scientific package is imported."""
import copy
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from contextlib import contextmanager
import tempfile
import os

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
S20 = ROOT / 'deliverables/learning_chain/b2_joint_sac_continuation_execution_20261009'


def load(name):
    path = OUT / (name + '.py')
    if not path.exists():
        raise AssertionError('Missing implemented module: ' + name)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.c = load('contract')
        self.config = json.loads((S20 / 'configuration.json').read_text(encoding='utf-8'))
        self.point = self.config['cases'][0]

    def fixture(self):
        r = math.radians(.25) / 2
        return dict(scope='frozen_development_evaluation', mode='F50', stage='zero',
                    case_id='J01', case_index=0, case=self.point,
                    simulation_case=self.c.case_kwargs(self.point), seed=2026092716,
                    comparison_key=self.config['common_key'], optimizer_steps_start=0,
                    optimizer_steps=0, policy_sha256='a' * 64, fault=None,
                    reference_problems=[], actual_reference_failed=False,
                    outcome=dict(task_outcome='FULL_SUCCESS', simulation_valid=True,
                                 physical_stopped=True, guard_violations=dict(contact=False, motion=False)),
                    task_end_time_s=7.88, peaks=dict(force_N=.024, torque_G_Nm=.0001),
                    trace=[dict(position_m=[75e-6, 75e-6, -.004],
                                quaternion_wxyz=[math.cos(r)**2, math.cos(r)*math.sin(r),
                                                 math.cos(r)*math.sin(r), -math.sin(r)**2])],
                    observation_schema=self.config['methods']['F50']['schema'],
                    source_session_outcome=dict(model_scope_qualified=False, training_admitted=False))

    def score(self):
        return dict(task_outcome='FULL_SUCCESS', task_time_s=7.88, simulation_valid=True,
                    physical_stopped=True, guard=False, peaks=dict(force_N=.024, torque_G_Nm=.0001))

    def audit(self, raw):
        return self.c.check_archive(raw, self.point, 'F0', self.config['common_key'],
                                    self.score(), self.config['methods']['F50']['schema'])

    def test_known_development_archive_does_not_upgrade_scope(self):
        result = self.audit(self.fixture())
        self.assertEqual(result['case_id'], 'J01')
        self.assertIs(result['historical_model_scope_qualified'], False)
        self.assertIs(result['historical_training_admitted'], False)

    def test_actual_tilt_mismatch_rejected_despite_same_case_name(self):
        raw = self.fixture(); raw['trace'][0]['quaternion_wxyz'] = [1., 0., 0., 0.]
        with self.assertRaises(ValueError): self.audit(raw)

    def test_task_key_mismatch_rejected(self):
        raw = self.fixture(); raw['comparison_key'] = 'other'
        with self.assertRaises(ValueError): self.audit(raw)

    def test_updates_during_frozen_evaluation_rejected(self):
        raw = self.fixture(); raw['optimizer_steps'] = 1
        with self.assertRaises(ValueError): self.audit(raw)

    def test_metric_disagrees_with_accepted_score_rejected(self):
        raw = self.fixture(); raw['task_end_time_s'] = 7.9
        with self.assertRaises(ValueError): self.audit(raw)

    def test_simulation_case_does_not_match_registered_pose_rejected(self):
        raw = self.fixture(); raw['simulation_case']['pitch_rad'] = 0.
        with self.assertRaises(ValueError): self.audit(raw)

    def test_invalid_outcome_is_not_reused(self):
        raw = self.fixture(); raw['outcome']['simulation_valid'] = False
        with self.assertRaises(ValueError): self.audit(raw)

    def test_ordinary_failure_consumes_case_and_allows_next(self):
        row = dict(case_id='J01', status='finished', healthy=True,
                   outcome=dict(task_outcome='TASK_FAILURE', simulation_valid=True,
                                physical_stopped=True, guard_violations=dict(contact=False, motion=False)))
        self.assertEqual(self.c.next_case([row], self.config['cases'])['id'], 'J02')

    def test_incomplete_attempt_cannot_be_retried(self):
        with self.assertRaises(ValueError):
            self.c.next_case([dict(case_id='J01', status='running')], self.config['cases'])

    def test_guard_or_unstopped_closes_package(self):
        row = dict(case_id='J01', status='finished', healthy=False,
                   outcome=dict(task_outcome='CONTACT_GUARD', simulation_valid=True,
                                physical_stopped=True, guard_violations=dict(contact=True, motion=False)))
        self.assertIsNone(self.c.next_case([row], self.config['cases']))

    def test_duplicate_reordered_case_rejected(self):
        with self.assertRaises(ValueError): self.c.next_case([dict(case_id='J02')], self.config['cases'])

    def test_old_training_grant_rejected(self):
        grant = json.loads((S20 / 'grant.json').read_text(encoding='utf-8'))
        with self.assertRaises(PermissionError): self.c.require_grant(grant, 'a' * 64, 'new-run')

    def test_unapproved_template_rejected(self):
        grant = self.c.grant_template('a' * 64, 'new-run')
        with self.assertRaises(PermissionError): self.c.require_grant(grant, 'a' * 64, 'new-run')

    def test_only_exact_new_zero_learning_limits_allowed(self):
        grant = self.c.grant_template('a' * 64, 'new-run')
        grant.update(explicit_user_authorized=True, human_evidence='New four-case approval', status='OPEN')
        self.c.require_grant(grant, 'a' * 64, 'new-run')
        grant['limits']['formal_updates'] = 1
        with self.assertRaises(PermissionError): self.c.require_grant(grant, 'a' * 64, 'new-run')


class EntryTests(unittest.TestCase):
    def setUp(self):
        self.r = load('baseline_rollout')

    def fake_session(self):
        class Session:
            cycle_id = 0
            done = False
            initial_trace_row = dict(position_m=[75e-6, 75e-6, -.004])
            initial = [75e-6, 75e-6, -.004]
            def __init__(self): self.requests = []
            def advance_cycle(self, action):
                self.requests.append(list(action)); self.cycle_id += 1
                self.done = self.cycle_id == 3
                return SimpleNamespace(
                    trace_row=dict(position_m=[75e-6, 75e-6, -.004 + self.cycle_id * 1e-6]),
                    action_log=dict(raw_action=list(action), requested_residual=[0.] * 6,
                                    applied_residual=[0.] * 6, experience_action=list(action),
                                    effective_command_delta=[0.] * 6,
                                    predicted_limited_command=[0., 0., .001, .002, 0., 0.]),
                    next_snapshot=SimpleNamespace(policy_observation=[0.] * 137,
                                                  residual_enabled=self.cycle_id % 2 == 0),
                    dt=.002, done=self.done, reward_terms=dict(total=0.),
                    cycle_peaks=dict(force_N=0., torque_G_Nm=0.))
        return Session()

    def snapshot(self):
        return SimpleNamespace(policy_observation=[0.] * 137, residual_enabled=True)

    def test_zero_residual_in_every_phase_preserves_baseline_commands(self):
        s = self.fake_session()
        result = self.r.drive_zero(s, self.snapshot(), clock=lambda: 0., stop=lambda: False,
                                   progress=lambda *args: None)
        self.assertEqual(s.requests, [[0., 0., 0., 0.]] * 3)
        self.assertEqual(len(result['transitions']), 3)
        self.assertTrue(result['transitions'][-1]['terminated'])
        self.assertEqual(result['actions'][0]['predicted_limited_command'][2], .001)

    def test_cycle_ceiling_stops_before_an_extra_cycle(self):
        s = self.fake_session()
        with self.assertRaises(RuntimeError):
            self.r.drive_zero(s, self.snapshot(), clock=lambda: 0., stop=lambda: False,
                              progress=lambda *args: None, cycle_limit=2)
        self.assertEqual(len(s.requests), 2)

    def test_reference_progress_receives_pre_action_snapshot(self):
        s = self.fake_session(); snapshot = self.snapshot(); seen = []
        self.r.drive_zero(s, snapshot, clock=lambda: 0., stop=lambda: False,
                          progress=lambda *args: seen.append(args))
        self.assertEqual(len(seen[0]), 5, 'Reference checks require the pre-action snapshot')
        self.assertIs(seen[0][4], snapshot)

    def test_failed_loop_keeps_all_partial_evidence(self):
        s = self.fake_session()
        with self.assertRaises(RuntimeError) as caught:
            self.r.drive_zero(s, self.snapshot(), clock=lambda: 0., stop=lambda: False,
                              progress=lambda *args: None, cycle_limit=2)
        evidence = getattr(caught.exception, 'episode_partial', None)
        self.assertIsNotNone(evidence, 'A closed failure must retain the complete observed prefix')
        self.assertEqual(len(evidence['trace']), 3)
        self.assertEqual(len(evidence['actions']), 2)

    def test_STOP_prevents_first_cycle(self):
        s = self.fake_session()
        with self.assertRaises(RuntimeError):
            self.r.drive_zero(s, self.snapshot(), clock=lambda: 0., stop=lambda: True,
                              progress=lambda *args: None)
        self.assertEqual(s.requests, [])

    def test_wall_deadline_prevents_cycle(self):
        values = iter([0., 1201.]); s = self.fake_session()
        with self.assertRaises(RuntimeError):
            self.r.drive_zero(s, self.snapshot(), clock=lambda: next(values), stop=lambda: False,
                              progress=lambda *args: None)
        self.assertEqual(s.requests, [])

    def test_nonzero_residual_cannot_be_labelled_pure_B2(self):
        log = dict(raw_action=[.01, 0., 0., 0.], requested_residual=[0.] * 6,
                   applied_residual=[0.] * 6, experience_action=[0.] * 4,
                   effective_command_delta=[0.] * 6)
        with self.assertRaises(ValueError): self.r.check_zero_log(log)

    def test_nonfinite_zero_action_evidence_rejected(self):
        log = dict(raw_action=[float('nan')] + [0.] * 3, requested_residual=[0.] * 6,
                   applied_residual=[0.] * 6, experience_action=[0.] * 4,
                   effective_command_delta=[0.] * 6)
        with self.assertRaises(ValueError): self.r.check_zero_log(log)

    def test_unauthorized_CLI_rejects_before_any_scientific_import(self):
        entry = OUT / 'baseline_entry.py'
        self.assertTrue(entry.is_file(), 'Missing implemented baseline entry')
        code = '''import sys,runpy,importlib.abc
class NoScience(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname.split('.')[0] in ('numpy','mujoco','torch','stable_baselines3'):
   raise AssertionError('SCIENCE_IMPORTED_BEFORE_AUTHORIZATION')
sys.meta_path.insert(0,NoScience())
sys.argv=[sys.argv[1],'--execute']
runpy.run_path(sys.argv[0],run_name='__main__')
'''
        result = subprocess.run([sys.executable, '-I', '-X', 'utf8', '-B', '-c', code, str(entry)],
                                capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('four-B2 grant', result.stderr)
        self.assertNotIn('SCIENCE_IMPORTED_BEFORE_AUTHORIZATION', result.stderr)
        self.assertFalse((OUT / 'execution').exists())


class ReviewRegressionTests(unittest.TestCase):
    def test_distinct_venv_worker_is_owned_before_GO(self):
        entry = load('baseline_entry')
        c = load('contract')
        sys.path.insert(0, str(ROOT))
        from tools.validation import process_parent as pp
        parent_pid = os.getpid(); launcher_pid = parent_pid + 100; native_pid = parent_pid + 101
        registered = dict(pid=parent_pid, parent_pid=1, image=sys._base_executable,
                          created_at=1., alive=True)
        launcher = dict(pid=launcher_pid, parent_pid=parent_pid, image='qualified-launcher.exe',
                        created_at=2., alive=True)
        native = dict(pid=native_pid, parent_pid=launcher_pid, image=sys._base_executable,
                      created_at=3., alive=True)
        records = {parent_pid: registered, launcher_pid: launcher, native_pid: native}
        events = []
        @contextmanager
        def windows_process(pid): yield records[pid]
        class Job:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def assign(self, handle): events.append(('launcher_owned', handle))
            def assign_pid(self, pid): events.append(('native_owned', pid))
            def active(self): return 0
            def stop(self): events.append(('stopped', None))
        with tempfile.TemporaryDirectory(dir=OUT) as td:
            base = Path(td) / 'gate'
            class Process:
                pid = launcher_pid; _handle = 'owned-popen-handle'; returncode = 0
                def poll(self):
                    if base.with_suffix('.go.json').exists():
                        self_go = c.read(base.with_suffix('.go.json'))
                        self.assert_go = self_go
                        events.append(('go', self_go['pid']))
                    return 0
                def wait(self, timeout=None): return 0
            def popen(command, **kwargs):
                proof = pp.validate_chain(expected_pid=parent_pid, registered_at=float(command[-1]),
                         now=float(command[-1]), child=native, parent=launcher, registered=registered,
                         python_image=sys._base_executable, launcher_image=command[0])
                c.write(base.with_suffix('.ready.json'), dict(proof=proof, registered_at=float(command[-1])))
                return Process()
            with patch.object(pp, 'windows_process', windows_process):
                result = entry.supervise(['qualified-launcher.exe'], base, 10,
                                         job_factory=Job, popen=popen)
            self.assertTrue(result['go_issued'])
            self.assertEqual(events[:2], [('launcher_owned', 'owned-popen-handle'), ('native_owned', native_pid)])
            self.assertEqual(c.read(base.with_suffix('.go.json'))['pid'], native_pid)

    def test_error_receipt_is_preserved_in_claimed_cost_ledger(self):
        entry = load('baseline_entry'); c = load('contract')
        ledger = dict(episodes=[dict(case_id='J01', status='claimed', healthy=False)])
        with tempfile.TemporaryDirectory(dir=OUT) as td:
            run = Path(td)
            c.write(run / 'receipt.json', dict(case_id='J01', status='error', healthy=False,
                    reset_attempted=1, reset_completed=1, control_cycles=27, physical_substeps=270))
            entry.collect_receipt(ledger, run)
            self.assertEqual(ledger['episodes'][0]['status'], 'error')
            self.assertEqual(ledger['episodes'][0]['physical_substeps'], 270)

    def test_runtime_metadata_drift_rejected_without_numerical_import(self):
        c = load('contract')
        with tempfile.TemporaryDirectory(dir=OUT) as td:
            site = Path(td); dist = site / 'numpy-2.1.3.dist-info'; dist.mkdir()
            meta = dist / 'METADATA'; meta.write_text('Name: numpy\nVersion: 2.1.3\n', encoding='utf8')
            rt = dict(site_packages=str(site), versions={'numpy': '2.1.3'}, inventories={},
                      package_paths={}, executable=sys.executable, base_executable=sys._base_executable,
                      prefix=sys.prefix, python='.'.join(map(str, sys.version_info[:3])))
            c.check_runtime(rt, check_interpreter=False)
            meta.write_text('Name: numpy\nVersion: 2.2.0\n', encoding='utf8')
            with self.assertRaises(ValueError): c.check_runtime(rt, check_interpreter=False)

    def test_unregistered_numerical_source_rejected(self):
        c = load('contract')
        with tempfile.TemporaryDirectory(dir=OUT) as td:
            root = Path(td); pkg = root / 'numpy'; pkg.mkdir(); (pkg / '__init__.py').write_text('')
            rt = dict(site_packages=str(root), versions={}, inventories={str(pkg): ['__init__.py']},
                      package_paths={'numpy': str(pkg / '__init__.py')})
            c.check_runtime(rt, check_interpreter=False)
            (pkg / 'unexpected.py').write_text('')
            with self.assertRaises(ValueError): c.check_runtime(rt, check_interpreter=False)


if __name__ == '__main__':
    unittest.main(verbosity=2)
