"""Independent fixtures for command bounds and world-frame wrench shifts."""

import numpy as np
import pytest


def test_command_clips_each_linear_and_angular_velocity_component():
    from tools.dynamics.safety import limit_command

    actual = limit_command(
        [5, -5, 0.2, -0.2, 10, -10], np.zeros(6), 1.0,
        [1, 2, 3, 4, 5, 6], np.full(6, 100.0),
    )
    assert isinstance(actual, np.ndarray)
    assert actual.shape == (6,)
    np.testing.assert_array_equal(actual, [1, -2, 0.2, -0.2, 5, -6])


def test_command_slew_uses_previous_command_and_component_acceleration():
    from tools.dynamics.safety import limit_command

    previous = np.array([0.4, -0.4, 0.1, -0.1, 0.9, -0.9])
    requested = np.array([-8, 8, 0.15, -0.15, 8, -8])
    actual = limit_command(requested, previous, 0.1, np.ones(6), [1, 2, 3, 4, 5, 6])
    np.testing.assert_allclose(actual, [0.3, -0.2, 0.15, -0.15, 1, -1])
    np.testing.assert_array_equal(previous, [0.4, -0.4, 0.1, -0.1, 0.9, -0.9])
    np.testing.assert_array_equal(requested, [-8, 8, 0.15, -0.15, 8, -8])


@pytest.mark.parametrize("name", ["requested", "previous", "velocity_limits", "acceleration_limits"])
@pytest.mark.parametrize("invalid", [np.zeros(5), np.zeros((6, 1)), [np.nan] * 6, [np.inf] * 6])
def test_command_rejects_wrong_shapes_and_nonfinite_vectors(name, invalid):
    from tools.dynamics.safety import limit_command

    arguments = dict(requested=np.zeros(6), previous=np.zeros(6), dt=0.1,
                     velocity_limits=np.ones(6), acceleration_limits=np.ones(6))
    arguments[name] = invalid
    with pytest.raises(ValueError):
        limit_command(**arguments)


@pytest.mark.parametrize("name", ["velocity_limits", "acceleration_limits"])
@pytest.mark.parametrize("invalid", [0.0, -1.0])
def test_command_rejects_nonpositive_limits(name, invalid):
    from tools.dynamics.safety import limit_command

    arguments = dict(requested=np.zeros(6), previous=np.zeros(6), dt=0.1,
                     velocity_limits=np.ones(6), acceleration_limits=np.ones(6))
    arguments[name][3] = invalid
    with pytest.raises(ValueError):
        limit_command(**arguments)


@pytest.mark.parametrize("dt", [0, -0.1, np.nan, np.inf, [0.1]])
def test_command_rejects_invalid_control_period(dt):
    from tools.dynamics.safety import limit_command

    with pytest.raises(ValueError):
        limit_command(np.zeros(6), np.zeros(6), dt, np.ones(6), np.ones(6))


@pytest.mark.parametrize("speed", [-1.01, 1.01])
def test_command_rejects_previous_velocity_outside_bounds(speed):
    from tools.dynamics.safety import limit_command

    with pytest.raises(ValueError):
        limit_command(np.zeros(6), [0, 0, 0, 0, 0, speed], 0.1, np.ones(6), np.ones(6))


def test_wrench_shift_to_grasp_point_has_positive_y_lever_moment():
    from tools.dynamics.safety import shift_wrench

    actual = shift_wrench([1, 0, 0, 0, 0, 0], [0, 0, 0], [0, 0, -0.0145])
    np.testing.assert_array_equal(actual, [1, 0, 0, 0, 0.0145, 0])


def test_wrench_shift_preserves_force_and_adds_existing_torque():
    from tools.dynamics.safety import shift_wrench

    wrench = np.array([0, 2, 0, 0.3, -0.4, 0.5])
    actual = shift_wrench(wrench, [1, 0, 0], [0, 0, 3])
    np.testing.assert_allclose(actual, [0, 2, 0, 6.3, -0.4, 2.5])
    np.testing.assert_array_equal(wrench, [0, 2, 0, 0.3, -0.4, 0.5])


@pytest.mark.parametrize("name,size", [("wrench", 6), ("source_world", 3), ("target_world", 3)])
@pytest.mark.parametrize("kind", ["short", "column", "nan", "infinity"])
def test_wrench_shift_rejects_wrong_shapes_and_nonfinite_vectors(name, size, kind):
    from tools.dynamics.safety import shift_wrench

    invalid = {"short": np.zeros(size - 1), "column": np.zeros((size, 1)),
               "nan": np.full(size, np.nan), "infinity": np.full(size, np.inf)}[kind]
    arguments = dict(wrench=np.zeros(6), source_world=np.zeros(3), target_world=np.zeros(3))
    arguments[name] = invalid
    with pytest.raises(ValueError):
        shift_wrench(**arguments)
