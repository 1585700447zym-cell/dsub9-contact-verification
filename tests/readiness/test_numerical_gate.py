import copy
import importlib
import pytest


def module():
    spec = importlib.util.find_spec('tools.validation.validate_training_readiness')
    assert spec is not None, 'The current-path readiness validator is not implemented'
    return importlib.import_module(spec.name)


def run():
    return {'name': 'example', 'case': {'name': 'example'}, 'command_world': [0, 0, .001, 0, 0, 0],
            'drive_duration_s': 1.2, 'metadata': {'segments': 256, 'config': {'timestep': .0002, 'control_period': .002}},
            'end_drive': {'position_m': [0, 0, 0], 'quaternion_wxyz': [1, 0, 0, 0]},
            'peaks': {'force_N': .01}, 'events': []}


def test_only_timestep_may_change():
    m = module(); a = run(); b = copy.deepcopy(a)
    b['metadata']['config']['timestep'] = .0001
    assert m.compare_pair(a, b)['pass']
    b['metadata']['config']['control_period'] = .001
    with pytest.raises(ValueError, match='metadata'): m.compare_pair(a, b)


def test_case_mismatch_is_rejected():
    m = module(); a = run(); b = copy.deepcopy(a); b['case']['name'] = 'different'
    with pytest.raises(ValueError, match='case'): m.compare_pair(a, b)


def test_event_mismatch_blocks_even_when_endpoint_matches():
    m = module(); a = run(); b = copy.deepcopy(a)
    b['events'] = [{'reason': 'FORCE_LIMIT'}]
    assert not m.compare_pair(a, b)['pass']


def test_historical_threshold_not_relaxed():
    m = module(); a = run(); b = copy.deepcopy(a)
    b['end_drive']['position_m'][0] = 21e-6
    assert not m.compare_pair(a, b)['pass']


def test_existing_attempt_and_path_escape_are_rejected(tmp_path):
    m = module(); (tmp_path/'existing').mkdir()
    with pytest.raises(FileExistsError): m.new_target(tmp_path, 'existing')
    with pytest.raises(ValueError): m.new_target(tmp_path, '../escape')


def test_input_hash_tampering_is_rejected(tmp_path):
    m = module(); p = tmp_path/'input.json'; p.write_text('original')
    digest = m.sha(p); p.write_text('changed')
    with pytest.raises(ValueError, match='changed'): m.verify_hashes(tmp_path, {'input.json': digest})
