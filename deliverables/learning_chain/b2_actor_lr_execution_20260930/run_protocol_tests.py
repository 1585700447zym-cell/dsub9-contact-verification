"""Evidence runner: prohibit real network forwards, optimizer steps and physics."""
import hashlib
import json
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
os.environ['MPLCONFIGDIR'] = str(ROOT / 'tmp/learning_mpl_cache')
from tools.learning.runtime import verify_runtime
verify_runtime(ROOT / 'tmp/mujoco_3_13_probe')
import torch
import mujoco
import pytest

calls = dict(model_forward=0, optimizer_step=0, physics=0)


def forbidden(kind):
    def fail(*args, **kwargs):
        calls[kind] += 1
        raise AssertionError('Forbidden in protocol preparation: ' + kind)
    return fail


torch.nn.Module._call_impl = forbidden('model_forward')
torch.optim.Adam.step = forbidden('optimizer_step')
for name in ('mj_forward', 'mj_step', 'mj_step1', 'mj_step2', 'mj_resetData', 'mj_resetDataKeyframe'):
    setattr(mujoco, name, forbidden('physics'))
tag = sys.argv[1]
report = HERE / (tag + '.xml')
if report.exists():
    raise FileExistsError('Evidence tag already exists')
paths = sys.argv[2:]
if not paths:
    raise ValueError('Explicit test paths required; never run unrestricted suite here')
code = pytest.main(['-q', '-p', 'no:cacheprovider', *paths, '--junitxml=' + str(report),
                    '--basetemp=' + str(HERE / (tag + '_work'))])
cases = list(ET.parse(report).getroot().iter('testcase'))
receipt = dict(exit_code=int(code), tests=len(cases), failures=sum(c.find('failure') is not None for c in cases),
    errors=sum(c.find('error') is not None for c in cases), forbidden_call_counts=calls,
    report_sha256=hashlib.sha256(report.read_bytes()).hexdigest(),
    test_ids=[c.attrib['classname']+'::'+c.attrib['name'] for c in cases])
(HERE / (tag + '_results.json')).write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
print(json.dumps({k:v for k,v in receipt.items() if k != 'test_ids'}))
sys.exit(1 if code or any(calls.values()) else 0)
