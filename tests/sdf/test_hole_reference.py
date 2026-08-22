import dataclasses

import numpy as np
import pytest

from tools.sdf.hole_reference import HoleParams, hole_distance, hole_gradient


PARAMS = HoleParams(
    bore_radius=0.000575,
    entry_radius=0.000675,
    entry_depth=0.00025,
    bore_depth=0.00450,
    outer_radius=0.00100,
)


def central_difference(function, point, step=1e-8):
    result = np.empty(3)
    for axis in range(3):
        offset = np.zeros(3)
        offset[axis] = step
        result[axis] = (function(point + offset) - function(point - offset)) / (2 * step)
    return result


def test_axis_is_free_space_inside_bore():
    assert hole_distance(np.array([0.0, 0.0, 0.002]), PARAMS) > 0.0


def test_main_bore_wall_is_zero_level_set():
    assert abs(hole_distance(np.array([0.000575, 0.0, 0.002]), PARAMS)) < 1e-12


def test_entry_section_uses_larger_radius():
    assert hole_distance(np.array([0.000625, 0.0, 0.00010]), PARAMS) > 0.0
    assert hole_distance(np.array([0.000625, 0.0, 0.00050]), PARAMS) < 0.0


def test_outer_wall_and_axial_ends_are_zero_level_sets():
    assert hole_distance(np.array([0.00100, 0.0, 0.00200]), PARAMS) == pytest.approx(0.0, abs=1e-15)
    assert hole_distance(np.array([0.00080, 0.0, 0.00450]), PARAMS) == pytest.approx(0.0, abs=1e-15)


def test_finite_annulus_corner_uses_euclidean_distance():
    # The query is 0.3 mm radially and 0.4 mm axially beyond the main annulus.
    assert hole_distance(np.array([0.00130, 0.0, 0.00490]), PARAMS) == pytest.approx(0.00050, abs=1e-15)


def test_entry_main_union_is_continuous_at_shoulder():
    point_below = np.array([0.000625, 0.0, PARAMS.entry_depth - 1e-9])
    point_at = np.array([0.000625, 0.0, PARAMS.entry_depth])
    point_above = np.array([0.000625, 0.0, PARAMS.entry_depth + 1e-9])
    assert hole_distance(point_below, PARAMS) == pytest.approx(1e-9, abs=1e-15)
    assert hole_distance(point_at, PARAMS) == pytest.approx(0.0, abs=1e-15)
    assert hole_distance(point_above, PARAMS) == pytest.approx(-1e-9, abs=1e-15)


@pytest.mark.parametrize(
    "point",
    [
        np.array([0.00059, 0.00002, 0.00200]),
        np.array([0.00095, 0.00010, 0.00300]),
        np.array([0.00120, 0.00010, 0.00480]),
        np.array([0.00072, 0.00008, 0.00010]),
    ],
)
def test_gradient_matches_central_difference_away_from_csg_ties(point):
    numerical = central_difference(lambda p: hole_distance(p, PARAMS), point)
    analytic = hole_gradient(point, PARAMS)
    np.testing.assert_allclose(analytic, numerical, atol=1e-7)


def test_axis_gradient_matches_symmetric_central_difference():
    point = np.array([0.0, 0.0, 0.002])
    numerical = central_difference(lambda p: hole_distance(p, PARAMS), point)
    np.testing.assert_allclose(hole_gradient(point, PARAMS), numerical, atol=1e-12)


@pytest.mark.parametrize(
    "changes",
    [
        {"bore_radius": 0.000675},
        {"entry_radius": 0.000575},
        {"entry_radius": 0.00100},
        {"outer_radius": 0.000675},
        {"entry_depth": 0.0},
        {"entry_depth": 0.00450},
        {"bore_depth": 0.00025},
        {"bore_radius": float("nan")},
        {"entry_radius": float("inf")},
        {"entry_depth": float("-inf")},
    ],
)
def test_invalid_parameters_are_rejected(changes):
    with pytest.raises(ValueError):
        dataclasses.replace(PARAMS, **changes)


@pytest.mark.parametrize(
    "point",
    [np.array([1.0, 2.0]), np.array([0.0, np.nan, 0.0])],
)
def test_invalid_query_points_are_rejected(point):
    with pytest.raises(ValueError):
        hole_distance(point, PARAMS)
