"""Stored drive-error release must not outrun the unchanged motion guards."""
import math
import pytest


def test_critical_drive_predicts_observed_release_speed_problem():
    from tools.learning.newton_damping import release_velocity_peak
    speed = release_velocity_peak(20000., 2*math.sqrt(20000.*.05), .05, .0001)
    assert speed == pytest.approx(.023266738769, rel=1e-9)
    assert speed > .02


def test_candidate_bounds_free_release_and_is_stable_at_original_step():
    from tools.learning.newton_damping import release_velocity_peak, explicit_drive_stable
    for stiffness, mass, ratio, lead, command, guard in [
        (20000., .05, 5., .00012, .001, .02),
        (2., .00002, 12., .01, .03, .5)]:
        damping = ratio*2*math.sqrt(stiffness*mass)
        bound = math.sqrt(3)*(release_velocity_peak(stiffness,damping,mass,lead)+command)
        assert bound < guard
        assert explicit_drive_stable(stiffness,damping,mass,.0002)


def test_discrete_release_including_command_feedforward_stays_below_guards():
    from tools.learning.newton_damping import discrete_release_peak
    linear = discrete_release_peak(20000.,5*2*math.sqrt(1000.),.05,.0002,.00012,.001)
    angular = discrete_release_peak(2.,12*2*math.sqrt(.00004),.00002,.0002,.01,.03)
    assert math.sqrt(3)*linear < .02
    assert math.sqrt(3)*angular < .5
    # Continuous damping alone would incorrectly bless this larger lead.
    excessive = discrete_release_peak(20000.,5*2*math.sqrt(1000.),.05,.0002,.0002,.001)
    assert math.sqrt(3)*excessive > .02


def test_excessive_explicit_damping_is_rejected_instead_of_called_safe():
    from tools.learning.newton_damping import explicit_drive_stable, release_velocity_peak
    assert not explicit_drive_stable(20000.,8*2*math.sqrt(20000.*.05),.05,.0002)
    assert not explicit_drive_stable(2.,20*2*math.sqrt(2.*.00002),.00002,.0002)
    with pytest.raises(ValueError):
        release_velocity_peak(1.,1.,1.,.1)
