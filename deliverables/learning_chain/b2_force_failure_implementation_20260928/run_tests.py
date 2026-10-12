"""Protocol tests only; blocks native execution, optimization and predictions."""
from pathlib import Path
import os,sys,json,hashlib,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
D=Path(__file__).resolve().parent
os.environ['MPLCONFIGDIR']=str(ROOT/'tmp/learning_mpl_cache')
os.environ['PYTHONDONTWRITEBYTECODE']='1'
from tools.learning.runtime import verify_runtime
verify_runtime(ROOT/'tmp/mujoco_3_13_probe')
import mujoco,torch,pytest
from tools.learning.sac_update import SACUpdater
from tools.learning.fixed_rotation_cycle import fixed_sources
calls=dict(optimizer=0,physics=0,prediction=0)
def forbidden(kind):
    def stop(*a,**kw):
        calls[kind]+=1;raise AssertionError('Forbidden during protocol verification: '+kind)
    return stop
torch.optim.Adam.step=forbidden('optimizer')
SACUpdater.predict=forbidden('prediction')
for name in ('mj_forward','mj_step','mj_step1','mj_step2','mj_resetData','mj_resetDataKeyframe'):
    setattr(mujoco,name,forbidden('physics'))
tag=sys.argv[1]
paths=sys.argv[2:] or ['tests/learning/test_'+n+'.py' for n in ('action','fixed_rotation','fixed_rotation_cycle',
    'runtime','repaired_runtime','repaired_cycle','bounded_contact','bounded_checkpoint','bounded_cycle',
    'bounded_sac_inputs','boundary_targets','force_failure_rules','force_failure_pipeline','force_failure_regressions')]
if len(sys.argv)==2:paths+=['deliverables/learning_chain/b2_bounded_cycle_20260927/retry_01/test_driver.py']
report=D/(tag+'.xml')
assert not report.exists(),'Use a new evidence tag.'
before=fixed_sources()
code=pytest.main(['-q','-p','no:cacheprovider',*paths,'--junitxml='+str(report)])
cases=list(ET.parse(report).getroot().iter('testcase'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
receipt=dict(exit_code=int(code),tests=len(cases),tests_with_failure_or_error=sum(bool(list(c)) for c in cases),
    source_sha256=before,
    forbidden_call_counts=calls,report_sha256=sha(report),runner_sha256=sha(Path(__file__)),
    test_ids=sorted(c.attrib['classname']+'::'+c.attrib['name'] for c in cases))
(D/(tag+'_binding.json')).write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in receipt.items() if k not in ('test_ids','source_sha256')}))
sys.exit(1 if code or any(calls.values()) or before!=fixed_sources() else 0)
