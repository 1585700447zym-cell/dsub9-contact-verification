"""Related protocols only; hard-block all model, optimizer and physics calls."""
import argparse,json,os,sys
from pathlib import Path
import xml.etree.ElementTree as ET
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(HERE))
os.environ['MPLCONFIGDIR']=str(ROOT/'tmp/learning_mpl_cache')
from tools.validation.run_actor_lr_comparison import select_qualified_runtime
select_qualified_runtime()
import torch,mujoco,pytest
calls=dict(model_forward=0,optimizer=0,physics=0)
def forbidden(kind):
    def fail(*a,**k):calls[kind]+=1;raise AssertionError('Related protocol forbids '+kind)
    return fail
torch.nn.Module._call_impl=forbidden('model_forward');torch.optim.Adam.step=forbidden('optimizer')
for name in ('mj_step','mj_step1','mj_step2','mj_forward','mj_resetData','mj_resetDataKeyframe'):setattr(mujoco,name,forbidden('physics'))
p=argparse.ArgumentParser();p.add_argument('--tag',required=True);a=p.parse_args()
if not a.tag.isidentifier():raise ValueError('Safe evidence tag required')
xml=HERE/(a.tag+'.xml')
if xml.exists() or (HERE/(a.tag+'.json')).exists():raise FileExistsError('Evidence tag already consumed')
paths=[HERE/'test_protocol.py',ROOT/'tests/learning/test_atomic_json.py',ROOT/'tests/learning/test_windows_parent.py',
    ROOT/'tests/learning/test_force_failure_rules.py']
code=pytest.main(['-q','-p','no:cacheprovider',*[str(x) for x in paths],
    '--junitxml='+str(xml),'--basetemp='+str(HERE/(a.tag+'_work'))])
cases=list(ET.parse(xml).getroot().iter('testcase'))
record=dict(tests=len(cases),exit_code=int(code),failures=sum(x.find('failure') is not None for x in cases),
    errors=sum(x.find('error') is not None for x in cases),actual_calls=calls)
with (HERE/(a.tag+'.json')).open('x',encoding='utf-8') as f:json.dump(record,f,indent=2)
print(json.dumps(record));raise SystemExit(1 if code or any(calls.values()) else 0)
