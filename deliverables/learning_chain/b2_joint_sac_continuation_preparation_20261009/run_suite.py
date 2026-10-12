"""All tests for this continuation adapter run with stdlib only."""
import importlib.abc, json, sys, unittest
from pathlib import Path
OUT = Path(__file__).resolve().parent; sys.path.insert(0, str(OUT))
class NoScience(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in ('numpy', 'torch', 'mujoco', 'stable_baselines3', 'gymnasium'):
            raise PermissionError('Scientific runtime forbidden in offline suite: ' + fullname)
sys.meta_path.insert(0, NoScience())
if __name__ == '__main__':
    suite = unittest.defaultTestLoader.discover(str(OUT), pattern='test_*.py')
    with (OUT / 'suite.log').open('w', encoding='utf8') as log:
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    forbidden = [k for k in sys.modules if k.split('.')[0] in ('numpy', 'torch', 'mujoco', 'stable_baselines3', 'gymnasium')]
    report = dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors), skipped=len(result.skipped),
                  successful=result.wasSuccessful() and not forbidden, forbidden_imports=forbidden, physics=0, learner_constructions=0,
                  checkpoint_loads=0, network_forwards=0, formal_updates=0, new_experience=0)
    (OUT / 'suite_final.json').write_text(json.dumps(report, ensure_ascii=False, sort_keys=True), encoding='utf8')
    print(json.dumps(report, ensure_ascii=False))
    if not report['successful']: raise SystemExit(1)
