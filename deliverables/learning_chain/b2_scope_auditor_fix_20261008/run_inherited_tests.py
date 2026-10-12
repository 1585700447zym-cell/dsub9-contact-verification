"""Run all six inherited audit/guard/observation tests against the revision."""
import importlib.abc
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

OUT = Path(__file__).resolve().parent
PARENT = OUT.parent / 'b2_pose_scope_preflight_20261008'
FORBIDDEN = {'mujoco', 'torch', 'stable_baselines3', 'tensorflow', 'jax', 'gymnasium'}
class OfflineOnly(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in FORBIDDEN:
            raise ImportError('Offline inherited tests prohibit ' + fullname)
sys.meta_path.insert(0, OfflineOnly())
sys.path.insert(0, str(OUT))
import repaired_assess
from run_preflight import check_binding
check_binding()
import test_assess
from test_review_regressions import ReviewRegressions

suite = unittest.TestSuite()
suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(test_assess))
for name in ('test_I2_guard_contradictions_rejected_for_ordinary_failure',
             'test_I3_missing_or_fabricated_observations_rejected',
             'test_I3_missing_information_prevents_training_route'):
    suite.addTest(ReviewRegressions(name))
# Test import selection only. The revised production module has its own name;
# no registered runner module is replaced during actual archive auditing.
with patch.dict(sys.modules, {'assess': repaired_assess}):
    result = unittest.TextTestRunner(verbosity=2).run(suite)
check_binding()
assert not any(k.split('.')[0] in FORBIDDEN for k in sys.modules)
raise SystemExit(0 if result.wasSuccessful() else 1)
