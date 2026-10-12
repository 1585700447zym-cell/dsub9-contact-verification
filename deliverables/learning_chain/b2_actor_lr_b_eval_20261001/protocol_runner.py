"""Explicit protocol suite; real models/optimizers/physics are blocked."""
import json,os,sys
from pathlib import Path
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT));os.environ['MPLCONFIGDIR']=str(ROOT/'tmp/learning_mpl_cache')
from tools.validation.run_actor_lr_comparison import select_qualified_runtime
select_qualified_runtime()
import torch,mujoco,pytest
calls=dict(model_forward=0,optimizer_step=0,physics=0)
def forbidden(kind):
    def fail(*a,**k):calls[kind]+=1;raise AssertionError('Forbidden in protocol test: '+kind)
    return fail
torch.nn.Module._call_impl=forbidden('model_forward');torch.optim.Adam.step=forbidden('optimizer_step')
for name in ('mj_step','mj_step1','mj_step2','mj_forward','mj_resetData','mj_resetDataKeyframe'):setattr(mujoco,name,forbidden('physics'))
tag=sys.argv[1];xml=HERE/(tag+'.xml')
if xml.exists():raise FileExistsError('Use a new test evidence tag')
paths=sys.argv[2:] or [str(HERE/'test_protocol.py')]
code=pytest.main(['-q','-p','no:cacheprovider',*paths,'--junitxml='+str(xml),'--basetemp='+str(HERE/(tag+'_work'))])
cases=list(ET.parse(xml).getroot().iter('testcase'))
result=dict(exit_code=int(code),tests=len(cases),failures=sum(c.find('failure') is not None for c in cases),
    errors=sum(c.find('error') is not None for c in cases),forbidden_call_counts=calls)
(HERE/(tag+'_results.json')).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result));raise SystemExit(1 if code or any(calls.values()) else 0)
