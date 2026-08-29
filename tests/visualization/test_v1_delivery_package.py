from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
import re

import pytest

from tests.v1_fixture_data import synthetic_matrix, write_synthetic_delivery
from tools.validation import run_v1_contact_validation as runner


ROOT = Path(__file__).resolve().parents[2]
DETAILED_GUIDE = (
    ROOT / "deliverables" / "chinese_visual_package" / "V1接触验证使用说明.md"
)
ENTRY_GUIDE = ROOT / "deliverables" / "chinese_visual_package" / "中文使用说明.md"


def test_cli_help_lists_every_default_output(capsys):
    with pytest.raises(SystemExit) as error:
        runner.main(["--help"])

    help_text = capsys.readouterr().out
    assert error.value.code == 0
    for name in (
        "v1_contact_traces.json",
        "v1_contact_traces.csv",
        "v1_timestep_convergence.json",
        "v1_contact_validation_report.md",
        "v1_contact_validation",
    ):
        assert name in help_text
    assert "--check-only" in help_text


def test_check_only_validates_complete_delivery_without_running_mujoco(
    tmp_path: Path, monkeypatch, capsys
):
    source_hash = hashlib.sha256(runner.SOURCE_CONTACT_RESULTS.read_bytes()).hexdigest()
    outputs = write_synthetic_delivery(tmp_path, source_hash)

    def forbidden_model_run():
        raise AssertionError("--check-only must not run MuJoCo")

    monkeypatch.setattr(runner, "run_v1_matrix", forbidden_model_run)
    status = runner.main(
        [
            "--check-only",
            "--trace-json",
            str(outputs["trace_json"]),
            "--trace-csv",
            str(outputs["trace_csv"]),
            "--convergence-json",
            str(outputs["convergence_json"]),
            "--chart-dir",
            str(outputs["chart_dir"]),
            "--report",
            str(outputs["report"]),
        ]
    )

    printed = capsys.readouterr().out
    assert status == 0
    assert "PASS" in printed
    assert "36" in printed


def test_generation_keeps_outputs_and_returns_success_when_acceptance_is_fail(
    tmp_path: Path, monkeypatch
):
    traces = list(synthetic_matrix())
    medium_index = next(
        index
        for index, trace in enumerate(traces)
        if trace.case.name == "x_offset_pos_100um" and trace.timestep_s == 0.0002
    )
    traces[medium_index] = replace(
        traces[medium_index],
        summary=replace(traces[medium_index].summary, termination="NUMERICAL_ERROR"),
    )
    monkeypatch.setattr(runner, "run_v1_matrix", lambda: tuple(traces))

    status = runner.main(
        [
            "--trace-json",
            str(tmp_path / "trace.json"),
            "--trace-csv",
            str(tmp_path / "trace.csv"),
            "--convergence-json",
            str(tmp_path / "convergence.json"),
            "--chart-dir",
            str(tmp_path / "charts"),
            "--report",
            str(tmp_path / "report.md"),
        ]
    )

    assert status == 0
    assert (tmp_path / "trace.json").is_file()
    assert "**FAIL**" in (tmp_path / "report.md").read_text(encoding="utf-8")


def test_chinese_entry_guide_links_to_detailed_guide_and_chart_directory():
    assert DETAILED_GUIDE.is_file()
    text = ENTRY_GUIDE.read_text(encoding="utf-8")
    local_targets = re.findall(r"\]\(([^)#]+)(?:#[^)]*)?\)", text)
    resolved = {
        (ENTRY_GUIDE.parent / target).resolve()
        for target in local_targets
        if not target.startswith(("http://", "https://"))
    }

    assert DETAILED_GUIDE.resolve() in resolved
    assert (
        ENTRY_GUIDE.parent / "charts" / "v1_contact_validation"
    ).resolve() in resolved
    assert all(path.exists() for path in resolved if path in {
        DETAILED_GUIDE.resolve(),
        (ENTRY_GUIDE.parent / "charts" / "v1_contact_validation").resolve(),
    })

