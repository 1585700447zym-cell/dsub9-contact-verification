from __future__ import annotations

import importlib
from pathlib import Path
import subprocess
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE = PROJECT_ROOT / "deliverables" / "chinese_visual_package"
FORMAL_CMD = PACKAGE / "启动正式SDF场景.cmd"
FALLBACK_CMD = PACKAGE / "启动免插件场景.cmd"


def run_python_launcher(mode: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.visualization.launch_viewer",
            "--mode",
            mode,
            "--check-only",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=30,
    )


@pytest.mark.parametrize(
    ("mode", "message"),
    [
        ("sdf", "正式 SDF 模型检查通过"),
        ("polygon32", "免插件 polygon32 模型检查通过"),
    ],
)
def test_check_only_compiles_model_from_unrelated_working_directory(
    mode: str, message: str
):
    """A launcher must not depend on the user's current terminal directory."""

    result = run_python_launcher(mode)

    assert result.returncode == 0, result.stdout + result.stderr
    assert message in result.stdout


def test_preflight_reports_missing_formal_plugin_in_chinese(tmp_path: Path):
    """A missing DLL must produce an actionable message before model compilation."""

    module = importlib.import_module("tools.visualization.launch_viewer")
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "dsub9_pair.xml").write_text("<mujoco/>", encoding="utf-8")

    issues = module.check_required_files("sdf", tmp_path)

    assert any("正式 SDF 插件不存在" in issue for issue in issues)


@pytest.mark.parametrize(
    ("path", "message"),
    [
        (FORMAL_CMD, "正式 SDF 模型检查通过"),
        (FALLBACK_CMD, "免插件 polygon32 模型检查通过"),
    ],
)
def test_double_click_cmd_locates_project_and_passes_check_only(
    path: Path, message: str
):
    """The user-facing CMD itself must work when invoked outside the repository."""

    result = subprocess.run(
        ["cmd.exe", "/d", "/c", str(path), "--check-only"],
        cwd=Path(PROJECT_ROOT.anchor),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=40,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert message in result.stdout
