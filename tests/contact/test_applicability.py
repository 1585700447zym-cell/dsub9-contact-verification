"""Checks independent geometry evidence and preserves the historical scan."""
import importlib
import math

import numpy as np
import pytest


def diagnostic():
    return importlib.import_module('tools.validation.diagnose_v1_applicability')


def test_signed_geometry_distinguishes_counterbore_from_main_bore():
    m = diagnostic()
    distances = m.material_distance(np.array([
        [0.000600, 0, 0.000100],
        [0.000600, 0, 0.000300],
        [0, 0, 0.001],
        [0.000625, 0, 0.000250],
    ]), m.DEFAULT_HOLE)
    assert distances == pytest.approx([0.000075, -0.000025, 0.000575, 0])


def test_grasp_pivot_translation_has_expected_sign_and_magnitude():
    m = diagnostic()
    r = np.array([[math.cos(.1), 0, math.sin(.1)], [0, 1, 0],
                  [-math.sin(.1), 0, math.cos(.1)]])
    origin = m.origin_for_pivot(np.zeros(3), r, np.array([0, 0, -.0145]))
    assert origin == pytest.approx([.0145 * math.sin(.1), 0, .0145 * (math.cos(.1)-1)])


def test_aligned_geometry_has_no_material_overlap():
    m = diagnostic()
    from tools.validation.run_contact_cases import ContactCase
    result = m.geometry_witness(ContactCase.aligned(), .004)
    assert result['sampled_max_material_overlap_m'] == 0


def test_combined_a_has_independent_geometric_overlap_near_bore_step():
    m = diagnostic()
    from tools.validation.run_contact_cases import ContactCase
    result = m.geometry_witness(ContactCase.combined(), .00018)
    assert result['sampled_max_material_overlap_m'] > 30e-6
    assert result['deepest']['pin'] == 'pin_05'
    assert result['deepest']['point_in_hole_m'][2] >= .00025


def test_diagnostic_reproduces_original_combined_a_without_changing_limit():
    m = diagnostic()
    from tools.validation.run_contact_cases import ContactCase, MAX_PENETRATION_M
    result = m.scan(ContactCase.combined())
    assert MAX_PENETRATION_M == 30e-6
    assert result['termination'] == 'EXCESS_PENETRATION'
    assert result['final_depth_m'] == pytest.approx(.00018)
    assert result['max_penetration_m'] == pytest.approx(31.89417233790987e-6, abs=1e-10)
    assert result['events']['first_exceed']['contacts'][0]['pair'] == ['pin_05', 'hole_sdf_05']


def test_sampling_grid_includes_target_and_rejects_invalid_step():
    m = diagnostic()
    assert m.depth_grid(.000025, .00001) == pytest.approx([0, .00001, .00002, .000025])
    with pytest.raises(ValueError):
        m.depth_grid(.004, 0)


def test_development_set_is_explicit_and_keeps_original_pressure_cases():
    m = diagnostic()
    cases = m.experiment_cases()
    assert len({c.name for c in cases}) == len(cases)
    assert {'combined_a', 'combined_b', 'aligned'} <= {c.name for c in cases}
    corners = [c for c in cases if c.name.startswith('dev_corner_')]
    assert len(corners) == 16
    assert all(abs(c.x_offset_m) == 25e-6 and abs(c.roll_rad) == math.radians(.5) for c in corners)


def test_output_cannot_overwrite_model_or_script(tmp_path):
    m = diagnostic()
    from tools.validation.run_contact_cases import FORMAL_MODEL
    for path in (FORMAL_MODEL, tmp_path/'outside.json'):
        with pytest.raises(ValueError):
            m.validate_output(path)


def test_collision_coverage_detects_missing_contact_at_tilted_full_depth():
    m = diagnostic()
    from tools.validation.run_contact_cases import ContactCase
    c = ContactCase.roll(math.radians(1.5))
    baseline = m.audit_pose(c, .004, initpoints=40, iterations=10)
    expanded = m.audit_pose(c, .004, initpoints=200, iterations=10)
    assert baseline['missing_overlap_pairs']
    assert baseline['contact_count'] == 0
    assert expanded['contact_count'] > 0


def test_surface_witness_uses_male_frame_and_agrees_with_reference_distance():
    m = diagnostic()
    from tools.validation.run_contact_cases import ContactCase
    from tools.sdf.hole_reference import hole_distance
    w = m.geometry_witness(ContactCase.combined(), .00018)['deepest']
    assert 'point_male_local_m' in w
    assert -hole_distance(np.array(w['point_in_hole_m']), m.DEFAULT_HOLE) == pytest.approx(w['sampled_max_material_overlap_m'])


def test_report_rejects_stale_source_fingerprints():
    from tools.reporting import report_v1_applicability as report
    with pytest.raises(ValueError, match='source'):
        report.verify_sources({'models/dsub9_pair.xml': 'incorrect_hash'})
