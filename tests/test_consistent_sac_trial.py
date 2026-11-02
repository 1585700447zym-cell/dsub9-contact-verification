"""Only schedule/cost and diagnostics-wrapper checks; no native environment."""
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np


def test_selected_budget_and_stage_order():
    from tools.learning.consistent_sac_trial import schedule,MAX_CYCLES
    jobs=schedule()
    assert len(jobs)==20 and sum(job['updates_after'] for job in jobs)==4000
    assert [sum(job['stage']==stage for job in jobs) for stage in ('baseline','warmup','online','development')]==[4,4,8,4]
    assert sum(job['publish'] for job in jobs)==12 and MAX_CYCLES*10*len(jobs)==3200000


def test_live_costs_merge_progress_instead_of_treating_zero_receipt_as_zero(tmp_path):
    from tools.learning.consistent_sac_trial import schedule,summarize_run
    folder=tmp_path/schedule()[0]['id'];folder.mkdir()
    (folder/'receipt.json').write_text(json.dumps(dict(reset_attempted=0,physical_substeps=0)))
    (folder/'progress.json').write_text(json.dumps(dict(reset_attempted=1,physical_substeps=1230,cycles=123)))
    result=summarize_run(tmp_path)
    assert result['initialization_attempts']==1 and result['physical_substeps']==1230
    assert result['cumulative_initializations']==420 and not result['counts_exact']
