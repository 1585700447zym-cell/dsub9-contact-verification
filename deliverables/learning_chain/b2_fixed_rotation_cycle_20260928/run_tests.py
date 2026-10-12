"""Related behavior tests with native stepping and optimizer calls blocked."""
from pathlib import Path
import sys
import json
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
D=Path(__file__).resolve().parent
from tools.learning.runtime import verify_runtime
verify_runtime(ROOT/'tmp/mujoco_3_13_probe')
import mujoco
import torch
import pytest
from tools.learning.fixed_rotation_cycle import fixed_sources as current_sources
from tools.learning.admission import digest
calls=dict(optimizer=0,physics=0)
def forbidden(kind):
    def stop(*args,**kwargs):
        calls[kind]+=1;raise AssertionError('Forbidden during qualification: '+kind)
    return stop
torch.optim.Adam.step=forbidden('optimizer')
for name in ('mj_forward','mj_step','mj_step1','mj_step2','mj_resetData','mj_resetDataKeyframe'):
    setattr(mujoco,name,forbidden('physics'))
paths=sys.argv[1:] or ['tests/learning/test_'+n+'.py' for n in (
    'action','fixed_rotation','fixed_rotation_cycle','runtime','repaired_runtime',
    'repaired_cycle','bounded_contact','bounded_checkpoint','bounded_cycle','bounded_sac_inputs','boundary_targets')]
if not sys.argv[1:]:paths+=['deliverables/learning_chain/b2_bounded_cycle_20260927/retry_01/test_driver.py']
before=current_sources();report=D/('red.xml' if sys.argv[1:] else 'tests.xml')
code=pytest.main(['-q','-p','no:cacheprovider',*paths,'--junitxml='+str(report)])
cases=list(ET.parse(report).getroot().iter('testcase'))
receipt=dict(source_sha256=before,exit_code=int(code),tests=len(cases),
    test_ids=sorted(r.attrib['classname']+'::'+r.attrib['name'] for r in cases),
    report_sha256=digest(report),runner_sha256=digest(Path(__file__)),forbidden_call_counts=calls)
(D/('red_binding.json' if sys.argv[1:] else 'test_binding.json')).write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
print('Forbidden call counts:',calls)
if code or any(list(r) for r in cases) or any(calls.values()) or before!=current_sources():sys.exit(1)
