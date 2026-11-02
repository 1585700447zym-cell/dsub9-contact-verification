"""Compatibility and explicit preparation-config semantics, no physical calls."""
def test_strict_overlength_rejection_preserves_old_guard_clear_flag():
    from tools.learning.episode_rules import STRICT,stamp_pending
    raw=dict(guard_facts=dict(simulation_valid=True,contact_reasons=[],motion_reasons=[],invalid_reasons=[]),
        outcome=dict(simulation_valid=True,physical_stopped=True,valid_for_learning=True,
        guard_violations=dict(contact=False,motion=False),task_outcome='TASK_FAILURE'),
        transitions=[{}]*13001,fault=None)
    record={}
    assert not stamp_pending(raw,record,STRICT)
    assert raw['guard_clear'] is False and record['guard_clear'] is False
    assert raw['outcome']['valid_for_learning'] is False


def test_preparation_config_names_only_unqualified_contact_as_a_hard_stop():
    from tools.learning.force_failure_preparation import force_config
    config=force_config()['execution']
    assert 'contact_guard' not in config['stop_on']
    assert 'unqualified_contact_guard' in config['stop_on']
    assert 'force_failure_frequency' in config['stop_on']
    assert config['preparation_only'] is True
    assert config['authorized_dynamic_starts']==config['authorized_optimizer_calls']==0
