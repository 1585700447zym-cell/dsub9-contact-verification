import importlib
import pytest


@pytest.mark.parametrize('valid,contact,motion,success,stopped,category,learn', [
    (True, False, True, False, True, 'MOTION_VIOLATION', True),
    (True, True, True, True, True, 'CONTACT_GUARD', True),
    (False, True, True, True, True, 'INVALID_SIMULATION', False),
    (True, False, False, True, True, 'FULL_SUCCESS', True),
    (True, False, False, True, False, 'STOP_NOT_QUALIFIED', False),
    (True, False, False, False, True, 'TASK_FAILURE', True),
    (True, True, False, False, False, 'CONTACT_GUARD', False),
])
def test_independent_facts_and_priority(valid, contact, motion, success, stopped, category, learn):
    result = importlib.import_module('tools.learning.outcome').classify_outcome(
        simulation_valid=valid, contact_guard=contact, motion_violation=motion,
        full_success=success, physical_stopped=stopped)
    assert result['simulation_valid'] is valid
    assert result['physical_stopped'] is stopped
    assert result['task_outcome'] == category
    assert result['valid_for_learning'] is learn
    assert result['guard_violations'] == {'contact': contact, 'motion': motion}
