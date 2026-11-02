import importlib
import numpy as np
import pytest


def test_four_axes_and_disabled_action():
    action = importlib.import_module('tools.learning.action')
    np.testing.assert_array_equal(action.map_residual([1, -1, 1, -1], enabled=True),
                                  [.00015, -.00015, 0, .005, -.005, 0])
    np.testing.assert_array_equal(action.map_residual([1, -1, 1, -1], enabled=False), np.zeros(6))


@pytest.mark.parametrize('value', [[np.nan, 0, 0, 0], [np.inf, 0, 0, 0], [0]*6, [1.01, 0, 0, 0]])
def test_invalid_input_rejected_even_when_masked(value):
    from tools.learning.action import map_residual
    with pytest.raises(ValueError):
        map_residual(value, enabled=False)


@pytest.mark.parametrize('phase,physical,pending,enabled', [
    ('INSERT', 'RUNNING', False, True), ('SEARCH', 'RUNNING', False, True),
    ('UNLOAD', 'RUNNING', False, False), ('WAIT_RECOVERY', 'STOPPING', False, False),
    ('SEARCH', 'RETRACT', False, False), ('FAILED', 'STOPPING', True, False),
    ('INSERT', 'TERMINAL', False, False), ('SEARCH', 'RUNNING', True, False),
])
def test_stage_permission(phase, physical, pending, enabled):
    from tools.learning.action import residual_permission
    assert residual_permission(phase, physical, pending=pending, guard_latched=False) is enabled
    assert residual_permission(phase, physical, pending=pending, guard_latched=True) is False


def test_common_stage_limits_preserve_z_yaw_and_log_command_effect():
    from tools.learning.action import compose_command
    base = [.00029, -.00029, .0005, .019, -.019, 0.]
    command, log = compose_command(base, [1, -1, 1, -1], phase='SEARCH', enabled=True,
                                   previous_limited=np.zeros(6), dt=.002)
    np.testing.assert_array_equal(command, [.0003, -.0003, .0005, .02, -.02, 0.])
    # Both requests are acceleration-limited to the same first command.
    np.testing.assert_array_equal(log['effective_command_delta'], np.zeros(6))
    np.testing.assert_array_equal(log['experience_action'], [1, -1, 1, -1])
    _, inactive = compose_command(base, [1, -1, 1, -1], phase='UNLOAD', enabled=False,
                                  previous_limited=np.zeros(6), dt=.002)
    np.testing.assert_array_equal(inactive['experience_action'], np.zeros(4))
