"""Run the recovery regression against saved old prepare_cycle, without editing source."""
from pathlib import Path
import sys,importlib.util,os
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT));os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'tmp/matplotlib_reference_search'))
from tools.validation.run_actor_lr_comparison import select_qualified_runtime
select_qualified_runtime()
spec=importlib.util.spec_from_file_location('tools.learning.reference_review_before',OUT/'before/session.py')
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
from tools.learning.reference_session import ReferenceSearchSession
ReferenceSearchSession.prepare_cycle=module.EpisodeSession.prepare_cycle
import pytest
raise SystemExit(pytest.main(['tests/task_variants/test_reference_search.py','-k','recovery_first','-q','--tb=short']))
