from importlib import import_module


def test_only_the_two_never_started_registered_jobs_are_continued():
    m=import_module('tools.validation.run_time_budget_search_remaining')
    jobs=m.schedule()
    assert [j['id'] for j in jobs]==['S450_M15_S2','S900_M15_S2']
    assert [j['search_speed_um_s'] for j in jobs]==[450,900]
    assert all(j['noise_seed']==2026110302 and j['updates_after']==0 and not j['publish'] for j in jobs)
    assert m.CUMULATIVE_BEFORE==453
