"""Selected offline tests only; never launch legacy physics integration suites."""
from pathlib import Path
import contextlib,json
from tools.validation.run_actor_lr_comparison import select_qualified_runtime
select_qualified_runtime()
import os
os.environ.setdefault('MPLCONFIGDIR',str(Path(__file__).resolve().parents[3]/'tmp/matplotlib_v4_verify'))
from tools.validation.run_v4_learning_pilot import input_hashes
before=input_hashes()
import pytest
ROOT=Path(__file__).resolve().parents[3]
folder=Path(__file__).resolve().parent
args=['tests/task_variants','tests/control']+['tests/learning/test_'+n+'.py' for n in
    ('action','reward','v4_learning','v4_checkpoint','sac_update','audited_replay','boundary_targets','learning_masks','tensor_masks')]
with (folder/'verification.txt').open('w',encoding='utf8') as f,contextlib.redirect_stdout(f),contextlib.redirect_stderr(f):
    result=pytest.main(args+['-q','--junitxml='+str(folder/'verification.xml')])
after=input_hashes()
(folder/'verification.json').write_text(json.dumps(dict(passed=result==0 and before==after,exit_code=int(result),command=args,
    source_sha256=before,source_unchanged=before==after,physics_episodes=0,formal_updates=0),indent=2),encoding='utf8')
raise SystemExit(result)
