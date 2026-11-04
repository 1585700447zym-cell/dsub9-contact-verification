"""First eight paired runs: scheduling/accounting only, no physics or NN."""
from copy import deepcopy
from importlib import import_module
import pytest


def api():
    return import_module('tools.validation.run_time_budget_search_batch')


def test_schedule_pairs_the_same_four_conditions_at_both_new_speeds():
    from tools.validation.run_noise50_yaw_repeat import schedule as prior
    jobs = api().schedule()
    assert len(jobs) == 8 and len({j['id'] for j in jobs}) == 8
    for index, old in enumerate(prior()):
        pair = jobs[2*index:2*index+2]
        assert [j['search_speed_um_s'] for j in pair] == [450, 900]
        for j in pair:
            assert j['case'] == old['case'] and j['seed'] == old['seed']
            assert j['noise_seed'] == old['noise_seed']
            assert j['passive_yaw_enabled'] is True
            assert j['publish'] is False and j['updates_after'] == 0


@pytest.mark.parametrize('key,value', [('search_speed_um_s',600), ('passive_yaw_enabled',False),
    ('publish',True), ('updates_after',1), ('noise_seed',123)])
def test_modified_or_unpaired_schedule_is_rejected(key, value):
    m = api(); jobs = deepcopy(m.schedule()); jobs[0][key] = value
    with pytest.raises(ValueError): m.validate_schedule(jobs)


def test_empty_summary_starts_at447_and_never_claims_completion(tmp_path, monkeypatch):
    m = api(); monkeypatch.setattr(m, 'OUT', tmp_path)
    s = m.summarize({'schedule':m.schedule()})
    assert s['cumulative_initializations'] == 447
    assert s['completed_episodes'] == 0 and s['counts_exact'] is False
    assert s['training_updates'] == 0


def test_existing_registration_is_not_overwritten(tmp_path, monkeypatch):
    m = api(); monkeypatch.setattr(m, 'OUT', tmp_path)
    p = tmp_path/'registration.json'; p.write_text('keep', encoding='utf-8')
    with pytest.raises(FileExistsError): m.prepare()
    assert p.read_text(encoding='utf-8') == 'keep'


def test_nonzero_exit_never_counts_as_complete(tmp_path, monkeypatch):
    import json
    m = api(); monkeypatch.setattr(m, 'OUT', tmp_path)
    jobs = m.schedule(); folder = tmp_path/'run'/jobs[0]['id']; folder.mkdir(parents=True)
    for name, value in [('job_result.json',dict(status='FINISHED')),
                        ('supervisor.json',dict(process_exit_confirmed=True,returncode=1))]:
        (folder/name).write_text(json.dumps(value), encoding='utf-8')
    assert m.summarize({'schedule':jobs})['completed_episodes'] == 0


@pytest.mark.parametrize('failed',[False,True])
def test_pair_stops_on_invalid_execution_but_accepts_valid_task_failures(tmp_path,monkeypatch,failed):
    m=api();monkeypatch.setattr(m,'OUT',tmp_path)
    pair=m.schedule()[:2]
    def launch(job):
        folder=tmp_path/'run'/job['id'];folder.mkdir(parents=True)
        m.write(folder/'job_result.json',dict(status='FAILED' if failed and job==pair[0] else 'FINISHED',outcome='TASK_FAILURE'))
        return dict(returncode=0,process_exit_confirmed=True)
    if failed:
        with pytest.raises(RuntimeError,match='no retry'):m.run_pair(pair,launch)
        assert (tmp_path/'STOP').exists()
    else:
        m.run_pair(pair,launch)
        assert not (tmp_path/'STOP').exists()
