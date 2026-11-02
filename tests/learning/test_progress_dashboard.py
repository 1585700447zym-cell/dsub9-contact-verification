"""Read-only dashboard reads never hold Windows replacement locks."""
import importlib,json,os
from pathlib import Path
import pytest


def api():return importlib.import_module('tools.validation.progress_dashboard')


def test_shared_reader_allows_actual_windows_replace(tmp_path):
    m=api();p=tmp_path/'status.json';p.write_text('{"old":true}')
    newer=tmp_path/'new.json';newer.write_text('{"new":true}')
    with m.shared_reader(p) as stream:
        os.replace(newer,p)
        assert json.loads(stream.read())=={'old':True}
    assert json.loads(p.read_text())=={'new':True}


def test_snapshot_handles_unstarted_run_without_claiming_training(tmp_path):
    data=api().snapshot(tmp_path)
    assert data['state']=='waiting' and data['updates'] is None
    assert data['attempts']==[]


def test_snapshot_distinguishes_recovered_warning_from_failure(tmp_path):
    run=tmp_path/'run';run.mkdir()
    (tmp_path/'started.json').write_text('{}')
    (tmp_path/'fault.log').write_text('atomic_json_replace_recovered: no learning action repeated')
    (run/'progress.json').write_text(json.dumps(dict(stage='training',episode=4,updates=12)))
    (run/'ledger.json').write_text(json.dumps(dict(status='healthy',dynamic_starts=8,attempts=[])))
    (run/'training_episodes').mkdir()
    (run/'training_episodes/update_budget.json').write_text('{"completed":144}')
    data=api().snapshot(tmp_path)
    assert data['state']=='running' and data['updates']==144
    (tmp_path/'process_exit.json').write_text('{"returncode":1}')
    (run/'failure.json').write_text('{"kind":"execution_failure"}')
    assert api().snapshot(tmp_path)['state']=='failed'


def test_bad_json_is_unavailable_not_fabricated(tmp_path):
    (tmp_path/'run').mkdir();(tmp_path/'run/progress.json').write_text('{')
    data=api().snapshot(tmp_path)
    assert data['updates'] is None and data['read_warnings']


def test_finite_policy_chart_values_only(tmp_path):
    p=tmp_path/'run/training';p.mkdir(parents=True)
    (p/'updates.json').write_text('[{"critic_batches":1,"critic_loss":2.0},{"critic_batches":2,"critic_loss":NaN}]')
    data=api().snapshot(tmp_path)
    assert data['loss']==[[1,2.0]]
