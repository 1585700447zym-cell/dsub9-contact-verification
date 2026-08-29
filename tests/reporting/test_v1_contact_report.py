from __future__ import annotations

from pathlib import Path

from tools.reporting.generate_v1_contact_report import (
    build_v1_report,
    write_v1_report,
)


def _trace_document() -> dict:
    return {
        "schema_version": 1,
        "source_contact_results_sha256": "e" * 64,
        "mujoco_version": "3.9.0",
        "collision_mode": "sdf",
        "contact_profile": "uncalibrated_diagnostic_v1",
        "solver": "Newton(iterations=100)",
        "spatial_step_m": 0.00001,
        "timestep_values_s": [0.0004, 0.0002, 0.0001],
        "trace_count": 36,
        "cases": [{"name": "x_offset_pos_100um"}],
        "traces": [],
        "limits": {
            "sweep": "prescribed quasi-static poses; no free dynamics",
            "force_calibration": "diagnostic numerical model only; uncalibrated",
        },
    }


def _comparison(status: str = "PASS") -> dict:
    failed = [] if status == "PASS" else ["peak_force_relative_pass"]
    return {
        "candidate_timestep_s": 0.0002,
        "common_sample_count": 100,
        "failed_checks": failed,
        "finite_pass": True,
        "max_penetration_delta_m": 0.000001,
        "no_numerical_error": True,
        "peak_force_relative_error": 0.0 if status == "PASS" else 0.25,
        "peak_force_relative_pass": status == "PASS",
        "peak_torque_relative_error": 0.02,
        "peak_torque_relative_pass": True,
        "primary_component_normalized_rmse": 0.03,
        "primary_component_rmse_pass": True,
        "primary_sign_pass": True,
        "relative_limit": 0.10,
        "status": status,
        "termination_candidate": "SUCCESS",
        "termination_depth_delta_m": 0.000001,
        "termination_depth_pass": True,
        "termination_match": True,
        "termination_reference": "SUCCESS",
        "zero_contact_absolute_pass": True,
    }


def _convergence_document(status: str = "PASS") -> dict:
    medium = _comparison(status)
    coarse = dict(_comparison("PASS"), candidate_timestep_s=0.0004, relative_limit=0.20)
    return {
        "schema_version": 1,
        "overall_status": status,
        "reference_timestep_s": 0.0001,
        "limits": {
            "medium_relative_limit": 0.10,
            "coarse_relative_limit": 0.20,
            "depth_delta_limit_m": 0.00001,
            "zero_contact_absolute_limit": 1e-12,
        },
        "cases": [
            {
                "case": "x_offset_pos_100um",
                "primary_component": "fx",
                "reference_final_depth_m": 0.004,
                "reference_max_penetration_m": 0.00002,
                "reference_peak_force_n": 1.234,
                "reference_peak_torque_nm": 0.005,
                "reference_termination": "SUCCESS",
                "status": status,
                "comparisons": {"0.0002": medium, "0.0004": coarse},
            }
        ],
    }


def test_report_contains_method_gates_failures_and_scientific_boundaries():
    trace_document = _trace_document()
    convergence_document = _convergence_document()

    report = build_v1_report(trace_document, convergence_document)

    for heading in (
        "## 验证范围",
        "## 模型与固定配置",
        "## 工况与深度网格",
        "## 接触曲线证据",
        "## 时间步收敛",
        "## 穿透与数值稳定性",
        "## 总体验收",
        "## 局限性与后续工作",
    ):
        assert heading in report
    assert convergence_document["overall_status"] in report
    assert trace_document["source_contact_results_sha256"] in report
    assert "未经实物标定" in report
    assert "自由动力学" in report


def test_failed_comparison_reports_case_timestep_measured_value_and_limit():
    report = build_v1_report(_trace_document(), _convergence_document("FAIL"))

    assert "x_offset_pos_100um" in report
    assert "0.0002 s" in report
    assert "peak_force_relative_pass" in report
    assert "25.00%" in report
    assert "10.00%" in report


def test_report_writer_uses_utf8_lf_and_one_final_newline(tmp_path: Path):
    output = tmp_path / "report.md"

    actual = write_v1_report(
        _trace_document(), _convergence_document(), output
    )

    raw = output.read_bytes()
    assert actual == output
    assert raw.decode("utf-8").endswith("\n")
    assert not raw.decode("utf-8").endswith("\n\n")
    assert b"\r\n" not in raw

