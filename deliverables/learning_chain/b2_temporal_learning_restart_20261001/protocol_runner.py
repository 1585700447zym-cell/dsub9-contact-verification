"""New contract protocols; all real forward/optimizer/physics APIs blocked."""
import argparse,io,json,os,sys,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];sys.path.insert(0,str(ROOT))
os.environ['MPLCONFIGDIR']=str(ROOT/'tmp/learning_mpl_cache')
from tools.validation.run_actor_lr_comparison import select_qualified_runtime
select_qualified_runtime()
import torch,mujoco
calls=dict(model_forward=0,optimizer=0,physics=0)
def forbidden(kind):
    def fail(*a,**k):calls[kind]+=1;raise AssertionError('Protocol forbids '+kind)
    return fail
torch.nn.Module._call_impl=forbidden('model_forward');torch.optim.Adam.step=forbidden('optimizer')
for name in ('mj_step','mj_step1','mj_step2','mj_forward','mj_resetData','mj_resetDataKeyframe'):setattr(mujoco,name,forbidden('physics'))
p=argparse.ArgumentParser();p.add_argument('--tag',required=True);p.add_argument('--filter',default='');a=p.parse_args()
if not a.tag.isidentifier():raise ValueError('Safe tag required')
stream=io.StringIO();suite=unittest.defaultTestLoader.discover(str(HERE),pattern='test_protocol.py')
if a.filter:
    def flat(s):
        for t in s:
            if isinstance(t,unittest.TestSuite):yield from flat(t)
            else:yield t
    suite=unittest.TestSuite(t for t in flat(suite) if a.filter in t.id())
    if not suite.countTestCases():raise ValueError('No matching protocol tests')
r=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
record=dict(tests=r.testsRun,failures=len(r.failures),errors=len(r.errors),actual_calls=calls)
for suffix,data in [('json',json.dumps(record,indent=2)),('txt',stream.getvalue())]:
    with (HERE/(a.tag+'.'+suffix)).open('x',encoding='utf-8') as f:f.write(data)
print(json.dumps(record));raise SystemExit(0 if r.wasSuccessful() and not any(calls.values()) else 1)
