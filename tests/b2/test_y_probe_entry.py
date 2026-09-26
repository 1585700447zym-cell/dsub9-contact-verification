"""Catch accidentally reusing X inputs or overwriting a preserved Y attempt."""
from dataclasses import asdict
import pytest


def test_y_entry_selects_y_reference_and_preserves_x_controller():
    from tools.validation.run_b2_y_probe import select_inputs
    folder, reference, case, controller = select_inputs()
    assert folder.name == 'verified_frozen_y100'
    assert case.name == 'y_offset_neg_100um'
    assert asdict(case) == reference['case']
    assert reference['case']['name'] == 'y_offset_neg_100um'
    assert controller.metadata()['config'] == reference['controller']['config']
    assert controller.metadata()['exit_gate'] == reference['controller']['exit_gate']
    assert controller.metadata()['probe'] == {'pause_s': 1.0, 'resume_s': 0.1}


def test_existing_attempt_is_rejected_before_dynamics(tmp_path):
    from tools.validation.run_b2_y_probe import new_target
    (tmp_path/'existing').mkdir()
    (tmp_path/'existing'/'evidence.txt').write_text('keep')
    with pytest.raises(FileExistsError):
        new_target(tmp_path, 'existing')
    assert (tmp_path/'existing'/'evidence.txt').read_text() == 'keep'


@pytest.mark.parametrize('tag', ['../escape', 'a/b', ''])
def test_invalid_tag_cannot_escape_output(tmp_path, tag):
    from tools.validation.run_b2_y_probe import new_target
    with pytest.raises(ValueError):
        new_target(tmp_path, tag)
    assert not list(tmp_path.iterdir())
