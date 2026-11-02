from copy import deepcopy
import importlib
import pytest
from tools.learning.admission import short_training_config


def api(): return importlib.import_module('tools.learning.b2_checkpoint_admission')


def record():
    m = api()
    return dict(version='b2_checkpoint_admission_v1', capability='bounded_checkpoint_probe',
        collection_admitted=True, update_admitted=True, restore_admitted=True, runnable_trainer=False,
        parent_sha256=m.PARENT_SHA256, config=short_training_config(), runtime={'test': 1},
        execution_contract=m.execution_contract(), source_sha256={'test': 'sha'},
        gates={k: True for k in m.GATES})


def test_checkpoint_qualification_is_separate_bounded_capability():
    m = api(); r = record()
    m.validate_record(r, current_sources=r['source_sha256'], runtime=r['runtime'])
    assert m.execution_contract()['max_probe_updates'] == 16
    assert m.execution_contract()['resume_boundary'] == 'whole_episode_audited_and_published'
    assert m.execution_contract()['first_engineering_short_train'] is False


@pytest.mark.parametrize('change', [dict(restore_admitted=False), dict(runnable_trainer=True),
    dict(parent_sha256='stale'), dict(source_sha256={}), dict(gates={}), dict(runtime={}),
    dict(execution_contract={}), dict(capability='full_training')])
def test_incomplete_or_extended_permission_rejected(change):
    r = record(); original = deepcopy(r); r.update(change)
    with pytest.raises(ValueError):
        api().validate_record(r, current_sources=original['source_sha256'], runtime=original['runtime'])


def test_restore_probe_cannot_change_preregistered_cases_or_budget():
    m = importlib.import_module('tools.validation.verify_sac_checkpoint')
    p = m.verification_protocol(); m.validate_protocol(p)
    assert len(p['attempts']) == 3 and p['before_save_updates'] == p['after_save_updates'] == 8
    for change in ({'before_save_updates': 7}, {'attempts': p['attempts'][:2]}, {'after_save_updates': 20}):
        bad = deepcopy(p); bad.update(change)
        with pytest.raises(ValueError): m.validate_protocol(bad)
