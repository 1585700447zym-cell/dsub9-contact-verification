"""Independent geometry checks for the diagnostic tip-footprint criterion."""
import math
import numpy as np
import pytest
from tools.validation.diagnose_b2_contacts import projected_tip_overhang


def test_aligned_clearance_and_known_lateral_overhang():
    assert projected_tip_overhang(np.zeros(2), np.eye(3), .0005, .000575) == pytest.approx(-75e-6)
    assert projected_tip_overhang(np.array([100e-6, 0]), np.eye(3), .0005, .000575) == pytest.approx(25e-6)


def test_tilted_disk_against_dense_independent_boundary_points():
    angle=.2
    r=np.array([[math.cos(angle),0,math.sin(angle)],[0,1,0],[-math.sin(angle),0,math.cos(angle)]])
    center=np.array([90e-6, -40e-6])
    t=np.linspace(0, 2*math.pi, 100001)
    points=center[:,None]+.0005*(r[:2,0,None]*np.cos(t)+r[:2,1,None]*np.sin(t))
    # Evaluate sampled rim points independently, one aperture face at a time.
    expected=max(np.max(np.array([math.cos(a),math.sin(a)]) @ points)-.000575
                 for a in np.arange(256)*2*math.pi/256)
    assert projected_tip_overhang(center,r,.0005,.000575) == pytest.approx(expected,abs=1e-11)
