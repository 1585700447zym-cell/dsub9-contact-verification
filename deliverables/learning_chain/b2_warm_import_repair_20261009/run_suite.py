"""Complete offline repair suite, including the unchanged joint-contract tests."""
import argparse
import json
from pathlib import Path
import sys
import time
import unittest
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--label',required=True);args=parser.parse_args()
    if not args.label.replace('_','').isalnum():raise ValueError('Simple evidence label required')
    log=HERE/(args.label+'.log');report=HERE/(args.label+'.json')
    if log.exists() or report.exists():raise FileExistsError('Preserve every test attempt')
    started=time.monotonic()
    suite=unittest.defaultTestLoader.discover(str(HERE),pattern='test_*.py')
    with log.open('x',encoding='utf8') as stream:result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    forbidden=[k for k in sys.modules if k.split('.')[0] in ('numpy','torch','mujoco','stable_baselines3')]
    data=dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),
        successful=result.wasSuccessful() and not forbidden,forbidden_imports=forbidden,wall_s=time.monotonic()-started,
        physics=0,learner_constructions=0,checkpoint_loads=0,network_forwards=0,updates=0,replay_publications=0)
    report.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(data,ensure_ascii=False));sys.exit(0 if data['successful'] else 1)
