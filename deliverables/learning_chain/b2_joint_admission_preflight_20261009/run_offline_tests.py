"""Only this candidate's offline suite, with an import deny gate."""
import importlib.abc
import json
from pathlib import Path
import sys
import unittest
OUT=Path(__file__).resolve().parent;sys.path.insert(0,str(OUT))
class NoPhysicsOrLearning(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if (fullname.split('.')[0] in {'mujoco','torch','stable_baselines3','gymnasium','tensorflow','jax'} or
                fullname in {'tools.learning.environment','tools.learning.guarded_environment','tools.learning.session'}):
            raise ImportError('Offline suite forbids native/learning runtime: '+fullname)
def main():
    sys.meta_path.insert(0,NoPhysicsOrLearning())
    suite=unittest.defaultTestLoader.discover(str(OUT),pattern='test_*.py')
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps(dict(status='PASS' if result.wasSuccessful() else 'FAIL',tests=result.testsRun,
        failures=len(result.failures),errors=len(result.errors),new_physics=0,training=0,
        forbidden_modules=[m for m in sys.modules if m.split('.')[0] in {'mujoco','torch','stable_baselines3'}])))
    return 0 if result.wasSuccessful() else 1
if __name__=='__main__':raise SystemExit(main())
