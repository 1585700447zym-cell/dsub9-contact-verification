"""A visual interface must preserve the existing numerical experiment."""
import importlib
import json
import numpy as np
import pytest

from tools.dynamics.cartesian import CartesianEnvironment
from tools.control.fixed_admittance import FixedAdmittance
from tools.validation.run_b1_baseline import run_episode
from tools.validation.run_contact_cases import ContactCase


def api():
    return importlib.import_module('tools.usage.visual_sim')


def test_display_has_separate_model_and_data():
    env = CartesianEnvironment(segments=32, contacts_enabled=False)
    row = env.reset(ContactCase.aligned())
    mirror = api().DisplayModel(env.model)
    mirror.update(row)
    mirror.model.opt.timestep = .1
    mirror.model.geom_rgba[:] = 0
    mirror.data.qpos[:] = 99
    assert env.model.opt.timestep == .0002
    assert np.any(env.model.geom_rgba)
    np.testing.assert_array_equal(env.data.qpos, row['position_m']+row['quaternion_wxyz'])


def test_visual_observer_does_not_change_episode():
    env = CartesianEnvironment(segments=32, contacts_enabled=False)
    case = ContactCase.aligned()
    expected = run_episode(env, case, FixedAdmittance(), max_time=.02, settle_time=.01)
    mirror = api().DisplayModel(env.model)
    observed = []
    original = env.step
    with api().observe_steps(env, lambda: None, lambda row: (mirror.update(row), observed.append(row))):
        actual = run_episode(env, case, FixedAdmittance(), max_time=.02, settle_time=.01)
    assert env.step == original
    assert actual['trace'] == expected['trace']
    assert actual['peaks'] == expected['peaks']
    assert len(observed) == actual['control_steps']


def test_visual_observer_preserves_b2_policy_trace():
    from tools.control.search_recovery import SearchConfig, SearchRecovery
    from tools.validation.run_b2_search import run_search_episode
    env = CartesianEnvironment(segments=32, contacts_enabled=False)
    case = ContactCase.aligned()
    config = SearchConfig(total_action_time_s=.02, settle_time_s=.01)
    expected = run_search_episode(env, case, SearchRecovery(config))
    mirror = api().DisplayModel(env.model)
    with api().observe_steps(env, lambda: None, mirror.update):
        actual = run_search_episode(env, case, SearchRecovery(config))
    assert actual['trace'] == expected['trace']
    assert actual['policy_events'] == expected['policy_events']
    assert actual['events'] == expected['events']


def test_closing_before_step_does_not_advance_and_restores_step():
    env = CartesianEnvironment(segments=32, contacts_enabled=False)
    env.reset(ContactCase.aligned())
    original = env.step
    def cancel():
        raise api().UserCancelled()
    with pytest.raises(api().UserCancelled):
        with api().observe_steps(env, cancel, lambda row: None):
            env.step(np.zeros(6))
    assert env.physical_steps == 0 and env.step == original


def test_output_always_uses_new_directory(tmp_path):
    first = api().new_output(tmp_path, 'b1', 'aligned')
    (first/'keep.txt').write_text('keep', encoding='utf-8')
    second = api().new_output(tmp_path, 'b1', 'aligned')
    assert first != second
    assert (first/'keep.txt').read_text(encoding='utf-8') == 'keep'


def test_replay_loader_rejects_bad_pose_and_missing_samples(tmp_path):
    p = tmp_path/'bad.json'
    p.write_text(json.dumps({'trace':[{'time_s':0, 'position_m':[float('nan'),0,0],
                                    'quaternion_wxyz':[1,0,0,0]}]}), encoding='utf-8')
    with pytest.raises(ValueError):
        api().load_record(p)


def test_pause_step_resume_controls_are_distinct():
    state = api().PlaybackControls()
    assert state.paused
    state.on_key(ord('N'))
    state.consume_keys()
    assert state.paused and state.allow_step()
    assert not state.allow_step()
    state.on_key(ord('P'))
    state.consume_keys()
    assert not state.paused and state.allow_step()
    state.on_key(ord('Q'))
    state.consume_keys()
    assert state.quit


@pytest.mark.parametrize('failure', ['report', 'hold_interrupt'])
def test_completed_result_survives_later_presentation_failure(tmp_path, monkeypatch, failure):
    from types import SimpleNamespace
    module = api()
    monkeypatch.setattr(module, 'OUTPUT', tmp_path)
    monkeypatch.setattr(module, 'source_hashes', lambda: {})
    monkeypatch.setattr(module, 'fingerprint', lambda: {})
    monkeypatch.setattr(module, 'reference_record', lambda *a: None)
    monkeypatch.setattr(module, 'run_episode', lambda env, case, controller:
                        run_episode(env, case, controller, max_time=.01, settle_time=.01))
    def report(*args):
        if failure == 'report':
            raise RuntimeError('synthetic chart failure')
    def hold(*args):
        if failure == 'hold_interrupt':
            raise KeyboardInterrupt()
    monkeypatch.setattr(module, 'session_report', report)
    window = SimpleNamespace(before_step=lambda: None, update=lambda *a: None, hold=hold)
    env = CartesianEnvironment(segments=32, contacts_enabled=False)
    case = ContactCase.aligned()
    env.reset(case)
    module.run_live(SimpleNamespace(policy='b1', close_when_done=False), env, case, window)
    folder = next(tmp_path.iterdir())
    saved = json.loads((folder/'session.json').read_text(encoding='utf-8'))
    assert saved['status'] == 'COMPLETE' and saved['result'] == 'run.json.gz'
    assert saved['result_sha256'] == module.sha(folder/'run.json.gz')
    assert not (folder/'partial_trace.json.gz').exists()
    if failure == 'report':
        assert saved['report_status'] == 'ERROR'
