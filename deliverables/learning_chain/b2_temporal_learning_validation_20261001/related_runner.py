"""Protocol suite only; no neural, optimizer or physics calls."""
import argparse,json,os,sys
from pathlib import Path
import xml.etree.ElementTree as ET
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(HERE))
os.environ['MPLCONFIGDIR']=str(ROOT/'tmp/learning_mpl_cache')
from tools.validation.run_actor_lr_comparison import select_qualified_runtime
select_qualified_runtime()
import torch,mujoco,pytest
calls=dict(model_forward=0,optimizer=0,physics=0)
def forbidden(kind):
    def fail(*a,**kw):calls[kind]+=1;raise AssertionError('Related protocol forbids '+kind)
    return fail
torch.nn.Module._call_impl=forbidden('model_forward');torch.optim.Adam.step=forbidden('optimizer')
for name in ('mj_step','mj_step1','mj_step2','mj_forward','mj_resetData','mj_resetDataKeyframe'):setattr(mujoco,name,forbidden('physics'))
p=argparse.ArgumentParser();p.add_argument('--tag',required=True);a=p.parse_args()
if not a.tag.isidentifier():raise ValueError('Safe evidence tag required')
xml=HERE/(a.tag+'.xml')
if xml.exists() or (HERE/(a.tag+'.json')).exists():raise FileExistsError('Evidence tag consumed')
paths=[HERE/'test_protocol.py']+[ROOT/'tests/learning'/('test_'+name+'.py') for name in ('atomic_json','windows_parent','force_failure_rules','boundary_targets','audited_replay','admitted_collection','actor_lr_engine')]
class QualifiedFixture:
    def pytest_collection_modifyitems(self,items):
        # The legacy fixture names an older package. Keep genuine runtime
        # verification, adapting only its path to the explicitly selected one.
        from tools.learning.runtime import verify_runtime,active_package
        for item in items:
            for fixture in item._fixtureinfo.name2fixturedefs.get('runtime',[]):
                fixture.func=lambda:verify_runtime(active_package())
code=pytest.main(['-q','-p','no:cacheprovider',*[str(p) for p in paths],'--junitxml='+str(xml),'--basetemp='+str(HERE/(a.tag+'_work'))],plugins=[QualifiedFixture()])
cases=list(ET.parse(xml).getroot().iter('testcase'));record=dict(tests=len(cases),exit_code=int(code),failures=sum(x.find('failure') is not None for x in cases),errors=sum(x.find('error') is not None for x in cases),actual_calls=calls)
with (HERE/(a.tag+'.json')).open('x',encoding='utf-8') as f:json.dump(record,f,indent=2)
print(json.dumps(record));raise SystemExit(1 if code or any(calls.values()) else 0)
