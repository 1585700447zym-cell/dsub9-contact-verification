"""Offline qualification only; no physical reset or step."""
from pathlib import Path
import contextlib,json,os,sys,time
OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
sys.path.insert(0,str(ROOT))
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'tmp/matplotlib_v4_requalification'))
from tools.validation.run_actor_lr_comparison import select_qualified_runtime
select_qualified_runtime()
from tools.validation.run_v4_learning_pilot import input_hashes
from tools.validation.run_clearance_preflight import write,now
import pytest
args=json.loads((ROOT/'deliverables/paper_comparison/v4_learning_pilot_20261006/verification.json').read_text(encoding='utf8'))['command']
args=[a for a in args if a!='-q' and not a.startswith('--junitxml')]
args+=['-q','--junitxml='+str(OUT/'verification.xml')]
before=input_hashes();started=time.monotonic()
with (OUT/'verification.txt').open('w',encoding='utf8') as stream,contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream):
    code=pytest.main(args)
after=input_hashes()
write(OUT/'verification.json',dict(passed=code==0 and before==after,exit_code=code,command=args,
    source_sha256=after,source_unchanged=before==after,wall_s=time.monotonic()-started,at=now(),
    dynamic_episodes=0,formal_updates=0,scope='related_offline_suite_synthetic_numeric_updates_only'))
print((OUT/'verification.txt').read_text(encoding='utf8'))
raise SystemExit(code if before==after else 2)
