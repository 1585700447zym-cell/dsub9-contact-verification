from __future__ import annotations

from pathlib import Path

import numpy as np

from tools.mesh.audit_geometry import step_vertex_bounds, stl_bounds


SOURCE = Path(__file__).parents[2] / "DSub9_Deliverables_V4"


def test_female_source_stl_has_known_export_offset():
    """The source STL's uncentred export frame is part of its known contract."""
    bounds = stl_bounds(SOURCE / "DSub9_Female_Refined_V3.STL")
    np.testing.assert_allclose(bounds.minimum, [0.0, 0.0, 0.0], atol=1e-6)
    np.testing.assert_allclose(bounds.maximum, [30.8, 12.55, 9.7], atol=2e-5)


def test_step_sources_use_mating_frames():
    """Using non-vertex STEP points would produce incorrect mating extents."""
    female = step_vertex_bounds(SOURCE / "DSub9_Female_Refined_V3.step")
    male = step_vertex_bounds(SOURCE / "DSub9_Male_TwoStageRearShell_V3.step")
    np.testing.assert_allclose(female.minimum, [-15.4, -6.275, 0.0])
    np.testing.assert_allclose(female.maximum, [15.4, 6.275, 9.7])
    np.testing.assert_allclose(male.minimum, [-15.4, -7.0, -22.0])
    np.testing.assert_allclose(male.maximum, [15.4, 7.0, 4.0])
