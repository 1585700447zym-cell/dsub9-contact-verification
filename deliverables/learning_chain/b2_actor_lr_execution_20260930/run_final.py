"""Reuse the preceding 133 protocol test paths plus this stage's five files."""
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
prior=json.loads((ROOT/'deliverables/learning_chain/b2_actor_lr_origin_20260930/final_strict_results.json').read_text(encoding='utf-8'))
paths={row.split('::')[0].replace('.','/')+'.py' for row in prior['test_ids']}
paths.update('tests/learning/'+name for name in ('test_actor_lr_engine.py','test_actor_lr_budget.py',
    'test_actor_lr_execution_contract.py','test_actor_lr_execution_gates.py','test_actor_lr_runner.py'))
assert all((ROOT/path).is_file() for path in paths)
raise SystemExit(subprocess.call([sys.executable,'-X','utf8','-B',str(HERE/'run_protocol_tests.py'),
    'final_protocol',*sorted(paths)],cwd=ROOT))
