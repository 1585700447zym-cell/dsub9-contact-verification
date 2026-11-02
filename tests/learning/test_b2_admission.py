"""Reject stale physics, unreviewed additions and incomplete B.2 qualifications."""
from copy import deepcopy
import importlib

import pytest


def api():
    return importlib.import_module('tools.learning.b2_admission')


def test_extension_allows_only_reviewed_additions():
    assert api().validate_extension({'old': 'a'}, {'old': 'a', 'new': 'b'},
                                    allowed_additions={'new'}) == ['new']


@pytest.mark.parametrize('current', [
    {'old': 'changed', 'new': 'b'}, {'new': 'b'},
    {'old': 'a', 'new': 'b', 'extra': 'c'}, {'old': 'a'},
])
def test_changed_missing_or_unreviewed_source_refuses_inheritance(current):
    with pytest.raises(ValueError):
        api().validate_extension({'old': 'a'}, current, allowed_additions={'new'})


def record():
    from tools.learning.admission import short_training_config
    return dict(version='b2_collection_admission_v1', capability='audited_collection_only',
        collection_admitted=True, runnable_trainer=False, parent_sha256=api().PARENT_SHA256,
        config=short_training_config(), runtime={'native': 'fixed'},
        source_sha256={'old': 'a', 'new': 'b'},
        added_sources=['new'], gates={'parent': True, 'runtime': True, 'config': True,
            'extension': True, 'tests': True, 'source_unchanged': True})


@pytest.mark.parametrize('field,value', [
    ('collection_admitted', 'true'), ('runnable_trainer', True),
    ('parent_sha256', 'untrusted'), ('runtime', {'native': 'changed'}),
    ('source_sha256', {'old': 'a'}), ('capability', 'sac_training'),
])
def test_bad_qualification_never_opens_sampling(field, value):
    r = record()
    r[field] = value
    with pytest.raises(ValueError):
        api().validate_record(r, current_sources={'old': 'a', 'new': 'b'},
                              runtime={'native': 'fixed'})


@pytest.mark.parametrize('gates', [{}, {'parent': True},
    {'parent': True, 'runtime': True, 'config': True, 'extension': True,
     'tests': 1, 'source_unchanged': True}])
def test_missing_or_nonboolean_gate_refuses_sampling(gates):
    r = record()
    r['gates'] = gates
    with pytest.raises(ValueError):
        api().validate_record(r, current_sources=r['source_sha256'], runtime=r['runtime'])


def test_explicit_frozen_configuration_is_required():
    r = record()
    r['config'] = deepcopy(r['config'])
    r['config']['domain']['roll_rad'] = .01
    with pytest.raises(ValueError):
        api().validate_record(r, current_sources=r['source_sha256'], runtime=r['runtime'])


def test_valid_qualification_has_no_learning_permission():
    r = record()
    api().validate_record(r, current_sources=r['source_sha256'], runtime=r['runtime'])
    assert r['runnable_trainer'] is False


@pytest.mark.parametrize('ids', [[], ['other'], ['sampled_zero', 'untrained_cut'],
    ['sampled_zero', 'center_plus_x', 'center_plus_x']])
def test_delivery_refuses_missing_or_duplicate_preregistered_attempts(tmp_path, ids, runtime):
    import json
    from tools.validation.verify_admitted_collection import audit_archives
    (tmp_path / 'protocol.json').write_text(json.dumps(dict(version='b2_collection_check_v1',
        seed=2026092609, attempts=[{'id': x} for x in ids])), encoding='utf-8')
    with pytest.raises(ValueError): audit_archives(tmp_path)


@pytest.mark.parametrize('change', ['id', 'qualification', 'scope', 'seed'])
def test_archive_identity_scope_and_qualification_cannot_be_substituted(change):
    from tools.validation import verify_admitted_collection as v
    case = dict(name='fixed', x_offset_m=0., y_offset_m=0., roll_rad=0., pitch_rad=0.,
                start_origin_z_m=-.004, target_depth_m=.004)
    item = dict(id='center_plus_x', case=case)
    raw = dict(episode_id='center_plus_x', case=deepcopy(case), qualification_sha256='expected', seed=7)
    if change == 'id': raw['episode_id'] = 'another'
    if change == 'qualification': raw['qualification_sha256'] = 'other'
    if change == 'scope':
        raw['case']['x_offset_m'] = item['case']['x_offset_m'] = .0001
    if change == 'seed': raw['seed'] = 8
    with pytest.raises(ValueError):
        v.validate_attempt(raw, item, seed=7, qualification_sha256='expected')


def test_archive_success_cannot_override_raw_protection_fact():
    from tools.validation import verify_admitted_collection as v
    raw = dict(guard_facts={'simulation_valid': True, 'contact_reasons': ['FORCE_LIMIT'],
                          'motion_reasons': []},
        final_session={'phase': 'STOPPING', 'task_finished': True, 'reason': 'GEOMETRIC_SUCCESS'},
        outcome={'simulation_valid': True, 'task_outcome': 'FULL_SUCCESS',
                 'guard_violations': {'contact': False, 'motion': False},
                 'physical_stopped': True, 'valid_for_learning': True})
    with pytest.raises(ValueError): v.validate_outcome(raw, stopped=True)
