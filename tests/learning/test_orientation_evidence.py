import math
import numpy as np


def test_relative_angle_ignores_quaternion_sign_and_normalizes():
    from tools.validation.analyze_residual_orientation import relative_angles
    angle = math.radians(2.5)
    q = [math.cos(angle/2), math.sin(angle/2), 0, 0]
    values = relative_angles([[1, 0, 0, 0], q, (-2*np.asarray(q)).tolist()], [1, 0, 0, 0])
    np.testing.assert_allclose(values, [0, angle, angle], atol=1e-13)


def test_same_nonidentity_orientation_has_zero_relative_rotation():
    from tools.validation.analyze_residual_orientation import relative_angles
    q = [math.cos(.2), 0, math.sin(.2), 0]
    np.testing.assert_allclose(relative_angles([q], q), [0], atol=1e-13)
