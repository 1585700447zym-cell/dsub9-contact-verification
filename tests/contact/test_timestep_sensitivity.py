from __future__ import annotations

from tools.validation.run_contact_cases import ContactCase, run_case


def test_halving_timestep_does_not_reverse_combined_outcome():
    coarse = run_case(ContactCase.combined(), 0.0002, "sdf")
    fine = run_case(ContactCase.combined(), 0.0001, "sdf")
    assert coarse.termination == fine.termination
    assert coarse.peak_signed_wrench.tx * fine.peak_signed_wrench.tx > 0.0
    assert coarse.spatial_step_m == coarse.speed_m_s * coarse.timestep_s
    assert fine.spatial_step_m == fine.speed_m_s * fine.timestep_s


def test_both_combined_cases_have_finite_bounded_termination():
    for case in (ContactCase.combined(), ContactCase.combined_b()):
        result = run_case(case, 0.0002, "sdf")
        assert result.termination in {
            "SUCCESS",
            "NO_PROGRESS",
            "EXCESS_PENETRATION",
            "NUMERICAL_ERROR",
        }
        assert result.termination != "NUMERICAL_ERROR"
