"""Synthetic stopped evidence only, no physical integration or neural source."""
from copy import deepcopy
import pytest


def converted_archive(tmp_path, speed):
    from tests.test_consistent_sac_audit import stopped_archive_fixture
    from tools.learning.time_budget_trial import protocol_config, VERSION
    from tools.learning.five_axis_contract import field_slices
    raw, receipt, reg, job, publish = stopped_archive_fixture(tmp_path)
    contract = protocol_config(speed); spans = field_slices()
    for target in (raw, receipt, reg):
        target['execution_contract'] = deepcopy(contract)
    raw.update(version=VERSION, observation_version=contract['observation_version'],
               time_budget_protocol=deepcopy(contract))
    raw.pop('learning_version')
    raw['evidence']['controller_events'] = []
    receipt['controller_config'] = deepcopy(contract['controller_config'])
    receipt['final_reason'] = 'UNLOAD_TIMEOUT'
    for field in raw['observation_schema']:
        if field['name'] in ('searches_remaining', 'recoveries_remaining'):
            field.update(scale=[1.], source='time_only_retry_permission')
    for row in raw['transitions']:
        for kind in ('observation', 'next_observation'):
            for name in ('searches_remaining', 'recoveries_remaining'):
                row[kind][spans[name].start] = 1.
        row['action_log'].update(contract_version=VERSION, search_xy_limit_m_s=speed / 1e6)
    publish()
    return raw, receipt, reg, job, publish


@pytest.mark.parametrize('speed', [450, 900])
def test_complete_new_archive_uses_full_existing_stop_and_domain_audit(tmp_path, speed):
    from tools.learning.time_budget_trial import audit_archive
    from tools.validation.consistent_sac_audit import audit_archive as old_audit
    _, _, reg, job, _ = converted_archive(tmp_path, speed)
    _, _, proof = audit_archive(tmp_path, reg, job, search_speed_um_s=speed)
    assert proof['verified'] and proof['stop']['final_native_samples'] == 10000
    assert proof['time_only_retry_features_verified']
    with pytest.raises(ValueError, match='binding'):
        old_audit(tmp_path, reg, job)


@pytest.mark.parametrize('tamper', ['budget', 'schema', 'limit', 'profile', 'old_failure',
                                  'old_risk_event', 'old_quota_event', 'missing_events'])
def test_new_archive_rejects_old_or_forged_protocol_evidence(tmp_path, tamper):
    from tools.learning.time_budget_trial import audit_archive
    from tools.learning.five_axis_contract import field_slices
    raw, receipt, reg, job, publish = converted_archive(tmp_path, 900)
    if tamper == 'budget':
        raw['transitions'][0]['observation'][field_slices()['searches_remaining'].start] = .5
    elif tamper == 'schema':
        next(f for f in raw['observation_schema'] if f['name'] == 'recoveries_remaining')['source'] = 'controller'
    elif tamper == 'limit':
        raw['transitions'][0]['action_log']['search_xy_limit_m_s'] = .00045
    elif tamper == 'profile':
        raw['transitions'][0]['action_log']['profile'] = 'G0'
    elif tamper == 'old_failure':
        receipt['final_reason'] = 'SEARCH_BUDGET_EXHAUSTED'
    elif tamper == 'missing_events':
        raw['evidence'].pop('controller_events')
    else:
        reason = 'LOADED_ROTATION_RISK' if tamper == 'old_risk_event' else 'SEARCH_BUDGET_EXHAUSTED'
        raw['evidence']['controller_events'].append(dict(time_s=0., phase='UNLOAD', reason=reason))
    publish()
    with pytest.raises(ValueError):
        audit_archive(tmp_path, reg, job, search_speed_um_s=900)
