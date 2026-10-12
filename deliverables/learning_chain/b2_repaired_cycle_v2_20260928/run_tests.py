"""Focused continuation checks; no actual optimization or physics permitted."""
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from tools.learning.runtime import verify_runtime
verify_runtime(ROOT/'tmp/mujoco_3_13_probe')
import mujoco
import torch
import pytest
from tools.learning.bounded_contact import current_sources
from tools.learning.repaired_cycle import DELIVERY
from tools.learning.admission import digest
from tools.learning.admitted_collection import _write_json

calls=dict(optimizer=0,physics=0)
def optimizer_forbidden(*args,**kwargs):
    calls['optimizer']+=1;raise AssertionError('Real optimization forbidden during qualification tests')
def physics_forbidden(*args,**kwargs):
    calls['physics']+=1;raise AssertionError('Physical execution forbidden during qualification tests')
torch.optim.Adam.step=optimizer_forbidden
for name in ('mj_forward','mj_step','mj_step1','mj_step2'):setattr(mujoco,name,physics_forbidden)
paths=['tests/learning/test_'+name+'.py' for name in (
    'runtime','repaired_runtime','repaired_cycle','bounded_contact','bounded_checkpoint','bounded_cycle','bounded_sac_inputs','boundary_targets')]
paths+=['deliverables/learning_chain/b2_bounded_cycle_20260927/retry_01/test_driver.py']
before=current_sources();report=DELIVERY/'tests.xml'
code=pytest.main(['-q','-p','no:cacheprovider',*paths,'--junitxml='+str(report)])
cases=list(ET.parse(report).getroot().iter('testcase'))
if code or any(list(r) for r in cases) or any(calls.values()) or before!=current_sources():
    raise SystemExit('Failed, skipped, unbound or forbidden work')
_write_json(DELIVERY/'test_binding.json',dict(source_sha256=before,exit_code=int(code),
    tests=len(cases),test_ids=sorted(r.attrib['classname']+'::'+r.attrib['name'] for r in cases),
    report_sha256=digest(report),runner_sha256=digest(Path(__file__)),forbidden_call_counts=calls))
