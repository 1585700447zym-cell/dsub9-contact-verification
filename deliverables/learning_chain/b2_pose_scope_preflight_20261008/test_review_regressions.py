"""Single final-review correction pass; all fixtures and children are inert."""
from copy import deepcopy
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest.mock import patch
from test_scope_preflight import OUT,ROOT,temporary_directory,module


class ReviewRegressions(unittest.TestCase):
    def test_prepared_runtime_inventory_has_canonical_order(self):
        from scope_contract import read
        binding=read(OUT/'candidate_binding.json')
        for name,inventory in binding['inventories'].items():
            with self.subTest(directory=name):self.assertEqual(inventory,sorted(inventory))

    def test_I1_relocated_entrypoint_rejected_before_claim(self):
        import run_preflight as runner
        with patch.object(runner,'OUT',OUT.with_name('copied_scope_runner')):
            with self.assertRaises(PermissionError):runner.require_registered_location()
        runner.require_registered_location()
        self.assertEqual(runner.CLAIMS,ROOT/'deliverables/learning_chain/b2_pose_scope_preflight_20261008/claims')

    def test_I2_guard_contradictions_rejected_for_ordinary_failure(self):
        from assess import assess_raw
        from synthetic_fixtures import fixture
        source=fixture(success=False)
        for damage in ('force','rotation','samples','cycle_sample','event','nonfinite'):
            raw=deepcopy(source)
            if damage=='force':raw['peaks']['force_N']=1e6
            elif damage=='rotation':raw['guard_facts']['max_rotation_from_start_rad']=1.
            elif damage=='samples':raw['guard_facts']['checked_substeps']=0
            elif damage=='cycle_sample':raw['cycles'][0]['result']['cycle_peaks']['samples']=0
            elif damage=='event':raw['events'].append(dict(time_s=1.,phase='STOPPING',reason='FORCE_LIMIT'))
            else:raw['peaks']['speed_m_s']=float('nan')
            with self.subTest(damage=damage),self.assertRaises(ValueError):
                assess_raw(raw,raw['spec'],{'binding_sha256':'fixture'})

    def test_I3_missing_or_fabricated_observations_rejected(self):
        from assess import assess_raw
        from synthetic_fixtures import fixture
        source=fixture(success=False)
        for damage in ('missing','vector','raw','schema'):
            raw=deepcopy(source)
            if damage=='missing':
                for cycle in raw['cycles']:
                    for snap in (cycle['before'],cycle['after'],cycle['result']['next_snapshot']):
                        snap.pop('policy_observation',None);snap.pop('policy_raw',None)
            elif damage=='vector':raw['cycles'][0]['before']['policy_observation'][0]=.7
            elif damage=='raw':raw['cycles'][0]['before']['policy_raw']={}
            else:raw['observation_schema']=[]
            with self.subTest(damage=damage),self.assertRaises(ValueError):
                assess_raw(raw,raw['spec'],{'binding_sha256':'fixture'})

    def test_I3_missing_information_prevents_training_route(self):
        import assess
        rows=[dict(id=c+'_'+arm,kind='dynamic',audit_passed=True,functional_success=True,
            outcome=dict(task_outcome='FULL_SUCCESS'),effect_coverage='OBSERVED',contact_coverage='OBSERVED')
            for c in ('P01','P02','P03','P04','J01','J02','J03','J04') for arm in ('zero','script')]
        info=assess.information_comparison(rows)
        self.assertEqual(info['status'],'INSUFFICIENT_COVERAGE')
        self.assertEqual(len(info['symmetric_pairs']),8)
        self.assertNotEqual(assess.choose_route(True,False,rows,info),'REVIEW_MATCHED_TRAINING_REGISTRATION')

    def test_I4_stalled_inert_audit_is_killed_by_production_deadline_guard(self):
        guard=module('deadline_guard');self.assertIsNotNone(guard,'Missing hard outer supervisor')
        with temporary_directory() as t:
            folder=Path(t);script=folder/'inert_audit.py'
            script.write_text('import sys,time\nfrom pathlib import Path\nsys.path.insert(0,'+repr(str(OUT))+')\n'
                'from deadline_guard import enter_gate\nenter_gate(*sys.argv[1:])\ntime.sleep(60)\n',encoding='utf-8')
            started=time.monotonic()
            with self.assertRaises(TimeoutError):
                guard.bounded_process([sys.executable,'-I','-X','utf8','-B',str(script)],folder/'gate',.6)
            receipt=__import__('json').loads((folder/'gate.supervisor.json').read_text())
            self.assertTrue(receipt['process_exit_confirmed'])
            self.assertTrue(receipt['go_issued'])
            self.assertLess(time.monotonic()-started,6)
            self.assertTrue(receipt['deadline_hit'])

    def test_I5_assignment_failure_terminates_owned_handle(self):
        guard=module('deadline_guard');self.assertIsNotNone(guard)
        import windows_job
        class BadJob(windows_job.Job):
            def assign(self,handle):raise OSError('synthetic assignment failure')
        with temporary_directory() as t:
            folder=Path(t)
            with self.assertRaises(OSError):
                guard.bounded_process([sys.executable,'-I','-B','-c','import time;time.sleep(60)'],folder/'gate',2,job_factory=BadJob)
            receipt=__import__('json').loads((folder/'gate.supervisor.json').read_text())
            self.assertTrue(receipt['owned_launcher_exit_confirmed'])
            self.assertFalse(receipt['go_issued'])

    def test_I4_outer_timeout_closes_only_this_launch_claim(self):
        import run_preflight as runner
        from execution_contract import write
        from scope_contract import read
        with temporary_directory() as t:
            root=Path(t);folder=root/'result';folder.mkdir();claims=root/'claims';claim=claims/('a'*64);claim.mkdir(parents=True)
            gate=root/'outer'
            identity=dict(output=str(folder),outer_gate=str(gate))
            write(claim/'identity.json',identity)
            write(folder/'ledger.json',dict(status='OPEN',static_attempts=9,dynamic_attempts=1,
                attempts=[dict(id='P01_zero',kind='dynamic',status='running',physical_substeps_lower_bound=0,
                               physical_substeps_upper_bound=145000)]))
            with patch.object(runner,'CLAIMS',claims):
                runner.close_interrupted(folder,'a'*64,gate,TimeoutError('inert audit stalled'))
                self.assertEqual(read(folder/'ledger.json')['status'],'CLOSED_SUPERVISOR_TIMEOUT')
                self.assertEqual(read(claim/'closed.json')['unused_dynamic_closed'],15)
                before=(folder/'ledger.json').read_bytes()
                runner.close_interrupted(folder,'a'*64,root/'unrelated_outer',TimeoutError('unrelated'))
                self.assertEqual((folder/'ledger.json').read_bytes(),before)


if __name__=='__main__':unittest.main(verbosity=2)
