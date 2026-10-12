"""Pure sampling protocol, with model/physics/project runtime imports blocked."""
import argparse,builtins,io,json,unittest
from pathlib import Path
calls=[];original=builtins.__import__
def guard(name,*a,**k):
    if name.split('.')[0] in ('torch','mujoco','stable_baselines3','tools'):
        calls.append(name);raise RuntimeError('Protocol cannot import a computation runtime')
    return original(name,*a,**k)
builtins.__import__=guard
p=argparse.ArgumentParser();p.add_argument('--tag',required=True,choices=['red','green','review_red','review_green','final_red','final_green']);args=p.parse_args()
HERE=Path(__file__).resolve().parent
suite=unittest.defaultTestLoader.discover(str(HERE),pattern='test_warmup_hold.py')
log=io.StringIO();result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
record=dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),
    forbidden_imports=calls,new_model_calls=0,new_physics=0,new_updates=0)
for suffix,payload in [('json',json.dumps(record,indent=2)),('txt',log.getvalue())]:
    with (HERE/(args.tag+'_protocol.'+suffix)).open('x',encoding='utf-8') as stream:stream.write(payload)
print(json.dumps(record));raise SystemExit(0 if result.wasSuccessful() and not calls else 1)
