"""Offline integration checks; existing physical data is replayed as test input."""
import argparse
from copy import deepcopy
import importlib.abc
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(r'D:\dsub9项目计划\first_stage_sim\.worktrees\dsub9-v1-contact-validation')
NEW=Path(__file__).resolve().parent
OLD=ROOT/'deliverables/learning_chain/b2_pose_scope_preflight_20261008'
RUN=ROOT/'deliverables/learning_chain/b2_pose_scope_execution_20261008/run'
FORBIDDEN={'mujoco','torch','stable_baselines3','gymnasium','tensorflow','jax'}
class OfflineOnly(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in FORBIDDEN:raise ImportError('Offline integration prohibits '+fullname)
sys.meta_path.insert(0,OfflineOnly())
parser=argparse.ArgumentParser();parser.add_argument('--implementation',type=Path,default=NEW)
args,rest=parser.parse_known_args();sys.path.insert(0,str(args.implementation))
import scope_contract as contract
import execution_contract as execution
import run_preflight as runner
import assess

class IntegrationTests(unittest.TestCase):
    def test_fresh_proposal_has_current_cumulative_and_no_training(self):
        c=contract.proposal()
        self.assertEqual(c['cumulative_dynamic'],209)
        self.assertEqual(c['proposed_limits']['cumulative_dynamic_if_all_run'],225)
        self.assertEqual(len(contract.attempt_specs(c)),25)
        self.assertFalse(c['static_authorized'] or c['dynamic_authorized'] or c['training_admitted'])

    def test_old_consumed_grant_cannot_authorize_new_scope(self):
        grant=contract.read(RUN/'grant.json')
        with self.assertRaises(ValueError):
            execution.validate_grant(grant,grant['binding_sha256'],contract.proposal())

    def test_registered_modules_use_new_directory(self):
        self.assertEqual(runner.REGISTERED_OUT,NEW)
        runner.require_registered_location()
        self.assertEqual(Path(assess.__file__).resolve(),NEW/'assess.py')

    def test_revised_numeric_comparison_is_used(self):
        import numpy as np
        try:
            assess.same(np.float64(.125),.125,'integrated scalar')
            assess.same(.125,np.float64(.125),'integrated scalar')
        except ValueError as exc:self.fail('Integrated auditor still rejects equal numeric types: '+repr(exc))
        for a,b in [(float('inf'),np.float64(float('inf'))),(np.uint64(2**63+1),float(2**63)),(True,np.float64(1))]:
            with self.assertRaises(ValueError):assess.same(a,b,'bad scalar')

    def test_actual_worker_audit_step_replays_live_typed_archive(self):
        audit=getattr(runner,'audit_completed_raw',None)
        self.assertTrue(callable(audit),'Worker audit bridge not yet implemented')
        candidate,binding=runner.check_binding()
        raw=assess.read_archive(RUN/'P01_zero.json.gz')
        original_pin=contract.sha(RUN/'P01_zero.json.gz')
        # Only producer identity is adapted in this in-memory TEST input. The
        # existing archive is not rebound, rewritten or counted as a new run.
        raw['binding_sha256']=contract.sha(runner.BINDING)
        import numpy as np
        for cycle in raw['cycles']:
            result=cycle['result']
            for name in ('progress','total'):result['reward_terms'][name]=np.float64(result['reward_terms'][name])
            key='unfiltered_stage_limited_total'
            result['action_log'][key]=[np.float64(v) for v in result['action_log'][key]]
        result=audit(raw,raw['spec'],binding)
        self.assertTrue(result['audit_passed'])
        self.assertTrue(result['functional_success'])
        self.assertEqual(result['observation']['vectors_verified'],3046)
        self.assertFalse(result['training_admitted'])
        self.assertEqual(contract.sha(RUN/'P01_zero.json.gz'),original_pin)

    def test_worker_bridge_rejects_old_producer_identity(self):
        audit=getattr(runner,'audit_completed_raw',None)
        self.assertTrue(callable(audit),'Worker audit bridge not yet implemented')
        _,binding=runner.check_binding()
        raw=assess.read_archive(RUN/'P01_zero.json.gz')
        with self.assertRaisesRegex(ValueError,'another implementation'):
            audit(raw,raw['spec'],binding)

    def test_current_count_and_stop_rules_are_durable(self):
        base=ROOT/'tmp/b2_scope_pure_test_fixtures';base.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base,delete=False) as folder:
            def fail(spec,entry):raise RuntimeError('Synthetic initialization failure; no engine')
            ledger=execution.execute_matrix(contract.proposal(),Path(folder),fail)
            self.assertEqual(ledger['cumulative_before'],209)
            self.assertEqual(ledger['dynamic_attempts'],0)
            self.assertEqual(ledger['unused_dynamic_closed'],16)
            self.assertFalse(ledger['retry_allowed'])

    def test_numerical_pin_table_bound_and_missing_or_wrong_pin_rejected(self):
        dependency=str(ROOT/'deliverables/paper_comparison/small_boundary_numeric_execution_20261008/prior_source_bindings.json')
        _,binding=runner.check_binding()
        with self.subTest(case='generated coverage'):
            self.assertTrue(dependency in binding['files'],'Numerical pin input is absent from the generated binding')
        original_read=runner.read
        for damage in ('missing','wrong_pin'):
            altered=deepcopy(binding)
            if damage=='missing':altered['files'].pop(dependency,None)
            else:altered['files'][dependency]='0'*64
            def controlled_read(path):
                return altered if Path(path)==runner.BINDING else original_read(path)
            with self.subTest(case=damage),patch.object(runner,'read',side_effect=controlled_read):
                with self.assertRaises(ValueError):runner.check_binding()

if __name__=='__main__':unittest.main(argv=[sys.argv[0]]+rest,verbosity=2)
