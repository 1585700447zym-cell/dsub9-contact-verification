import importlib.util

def classify(**kwargs):
    spec=importlib.util.find_spec('tools.validation.run_native313_matrix')
    assert spec is not None, 'Versioned matrix runner missing'
    from tools.validation.run_native313_matrix import classify_episode
    base=dict(termination='NO_PROGRESS',phase='STOPPING',events=[],finite=True,stopped=True,safe=False,final_geometry=False)
    base.update(kwargs)
    return classify_episode(**base)

def test_normal_failure_is_not_numerical_failure_but_unstopped_is_blocking():
    a=classify(safe=True)
    assert a['category']=='VALID_TASK_FAILURE' and a['candidate_data_valid']
    b=classify(stopped=False,safe=True)
    assert b['category']=='STOP_NOT_QUALIFIED' and not b['candidate_data_valid']

def test_original_success_cannot_hide_new_invalid_or_unsettled_state():
    for kw in [dict(finite=False),dict(events=[{'reason':'INVALID_PENETRATION'}]),dict(stopped=False)]:
        a=classify(termination='GEOMETRIC_SUCCESS',safe=True,final_geometry=True,**kw)
        assert not a['full_success'] and not a['candidate_data_valid']
    assert not classify(termination='NO_PROGRESS',safe=True,final_geometry=True)['full_success']

def test_guard_failure_needs_guard_event_and_safe_success_cannot_be_claimed():
    assert not classify()['candidate_data_valid']
    a=classify(events=[{'reason':'FORCE_LIMIT'}])
    assert a['category']=='VALID_GUARD_FAILURE' and a['candidate_data_valid'] and not a['full_success']
