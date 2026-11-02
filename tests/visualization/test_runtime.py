from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys

import mujoco
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_RESULTS_SHA256 = (
    "ac767ea63a7e8a6866a974728a1256e688832003076170e270cd181e5c9d65ff"
)


def runtime_module():
    return importlib.import_module("tools.visualization.runtime")


def test_find_project_root_from_delivery_subdirectory():
    """A wrong parent-depth assumption must not break double-click launchers."""

    runtime = runtime_module()
    start = PROJECT_ROOT / "deliverables" / "chinese_visual_package"

    assert runtime.find_project_root(start) == PROJECT_ROOT


def test_find_project_root_rejects_unrelated_directory(tmp_path: Path):
    """An unrelated working directory must produce a useful Chinese failure."""

    runtime = runtime_module()

    with pytest.raises(FileNotFoundError, match="无法定位项目根目录"):
        runtime.find_project_root(tmp_path)


def test_pose_sets_free_joint_without_stepping_dynamics():
    """Visualization must prescribe a pose instead of integrating dynamics."""

    runtime = runtime_module()
    model = runtime.load_model("polygon32")
    data = mujoco.MjData(model)

    runtime.apply_pose(model, data, runtime.POSE_CASES["x_offset_pos_100um"])

    assert data.qpos[0] == pytest.approx(0.0001)
    assert data.qpos[1] == pytest.approx(0.0)
    assert data.qpos[2] == pytest.approx(0.0)
    assert data.qpos[3:7].tolist() == pytest.approx([1.0, 0.0, 0.0, 0.0])
    assert data.time == 0.0


@pytest.mark.parametrize(
    ("mode", "expected_plugins", "expected_geoms"),
    [("sdf", 1, 140), ("polygon32", 0, 707)],
)
def test_each_mode_loads_with_expected_plugin_isolation_in_fresh_process(
    mode: str, expected_plugins: int, expected_geoms: int
):
    """A fallback regression must not silently register the formal SDF plugin."""

    probe = """
import json
import sys
from tools.visualization.runtime import load_model

model = load_model(sys.argv[1])
print(json.dumps({"nplugin": model.nplugin, "ngeom": model.ngeom}))
"""
    result = subprocess.run(
        [sys.executable, "-c", probe, mode],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {
        "nplugin": expected_plugins,
        "ngeom": expected_geoms,
    }


def test_input_hashes_cover_protected_results_and_all_collision_assets():
    """A generator overwriting reviewed inputs must be detectable."""

    runtime = runtime_module()
    hashes = runtime.input_hashes()
    results = PROJECT_ROOT / "reports" / "contact_validation_results.json"

    assert hashes["reports/contact_validation_results.json"] == EXPECTED_RESULTS_SHA256
    assert hashes["reports/contact_validation_results.json"] == hashlib.sha256(
        results.read_bytes()
    ).hexdigest()
    collision_paths = [key for key in hashes if key.startswith("assets/collision/")]
    assert len(collision_paths) == 696

