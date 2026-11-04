"""Guard the authorized repeat batch; no native environment or network calls."""
from copy import deepcopy
import importlib
import pytest


def runner():
    return importlib.import_module('tools.validation.run_noise50_yaw_repeat')


def test_schedule_has_two_new_tapes_for_each_original_pose():
    jobs = runner().schedule()
    assert len(jobs) == 4 and len({j['id'] for j in jobs}) == 4
    for sign, initial_seed in [('YAW_P15', 2026092718), ('YAW_M15', 2026092719)]:
        selected = [j for j in jobs if j['case']['name'] == sign]
        assert {j['noise_seed'] for j in selected} == {2026110301, 2026110302}
        assert all(j['seed'] == initial_seed and j['passive_yaw_enabled'] is True
                   and j['publish'] is False and j['updates_after'] == 0 for j in selected)


@pytest.mark.parametrize('key,value', [('passive_yaw_enabled', False), ('publish', True),
                                     ('updates_after', 1), ('noise_seed', 2026103001)])
def test_request_rejects_a_changed_or_old_trial(key, value):
    mod = runner()
    jobs = deepcopy(mod.schedule()); jobs[0][key] = value
    with pytest.raises(ValueError):
        mod.validate_schedule(jobs)


def test_cost_summary_uses_443_and_never_certifies_partial_completion(tmp_path, monkeypatch):
    mod = runner(); monkeypatch.setattr(mod, 'OUT', tmp_path)
    result = mod.summarize({'schedule': mod.schedule()})
    assert result['cumulative_initializations'] == 443
    assert result['completed_episodes'] == 0 and result['counts_exact'] is False
    assert result['training_updates'] == 0


def test_prepare_never_overwrites_an_existing_registration(tmp_path, monkeypatch):
    mod = runner(); monkeypatch.setattr(mod, 'OUT', tmp_path)
    p = tmp_path/'registration.json'; p.write_text('keep', encoding='utf-8')
    with pytest.raises(FileExistsError):
        mod.prepare()
    assert p.read_text(encoding='utf-8') == 'keep'


def test_yaw_on_audit_rejects_missing_feedback_evidence():
    mod = runner()
    with pytest.raises(ValueError):
        mod.verify_active_yaw({'trace': []})


def test_nonzero_worker_exit_is_not_a_completed_episode(tmp_path, monkeypatch):
    import json
    mod = runner(); monkeypatch.setattr(mod, 'OUT', tmp_path)
    jobs = mod.schedule(); folder = tmp_path/'run'/jobs[0]['id']; folder.mkdir(parents=True)
    (folder/'job_result.json').write_text(json.dumps({'status': 'FINISHED'}), encoding='utf-8')
    (folder/'supervisor.json').write_text(json.dumps({'process_exit_confirmed': True, 'returncode': 1}), encoding='utf-8')
    result = mod.summarize({'schedule': jobs})
    assert result['completed_episodes'] == 0
