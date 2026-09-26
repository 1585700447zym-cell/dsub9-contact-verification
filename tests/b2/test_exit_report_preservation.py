"""Reporting must never overwrite a raw trial, including failed preflights."""
import json
import pytest
from tools.reporting import report_b2_exit_gate as report


@pytest.mark.parametrize('marker', ['runs', 'source_snapshot', 'results_index.json'])
def test_report_rejects_existing_raw_trial(tmp_path, marker):
    trial = tmp_path / 'trial'
    trial.mkdir()
    if marker.endswith('.json'):
        (trial / marker).write_text('{"status":"PREFLIGHT_FAILED"}', encoding='utf-8')
    else:
        (trial / marker).mkdir()
    with pytest.raises(FileExistsError):
        report.check_output(trial, [tmp_path/'x', tmp_path/'y'])


def test_report_rejects_input_folder_even_without_index(tmp_path):
    with pytest.raises(FileExistsError):
        report.check_output(tmp_path/'x', [tmp_path/'x', tmp_path/'y'])


def test_only_same_comparison_can_be_regenerated(tmp_path):
    output = tmp_path/'report'
    output.mkdir()
    inputs = [tmp_path/'x', tmp_path/'y']
    (output/'results_index.json').write_text(json.dumps({
        'method':'two new V2 dynamics runs vs preserved V1 records',
        'input_tags':['x','y']}), encoding='utf-8')
    report.check_output(output, inputs)
    with pytest.raises(FileExistsError):
        report.check_output(output, [tmp_path/'other_x', tmp_path/'y'])
