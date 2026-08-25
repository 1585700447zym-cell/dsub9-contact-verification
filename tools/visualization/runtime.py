"""Shared, read-only model loading and prescribed-pose utilities."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import functools
import hashlib
import math
import os
from pathlib import Path
from typing import Iterator, Literal

import mujoco


CollisionMode = Literal["sdf", "polygon32"]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FORMAL_MODEL = Path("models/dsub9_pair.xml")
FALLBACK_MODEL = Path("build/dsub9_pair_polygon32.xml")
PLUGIN_RELATIVE_PATH = Path("build/dsub9_hole_sdf/Release/dsub9_hole_sdf.dll")
CONTACT_RESULTS = Path("reports/contact_validation_results.json")


@dataclass(frozen=True)
class PoseCase:
    """One prescribed male-body pose in world/task coordinates."""

    name: str
    origin_z_m: float
    x_offset_m: float = 0.0
    y_offset_m: float = 0.0
    roll_rad: float = 0.0
    pitch_rad: float = 0.0

    def quaternion_wxyz(self) -> tuple[float, float, float, float]:
        """Return wxyz for R=Ry(pitch)@Rx(roll)."""

        cr = math.cos(self.roll_rad / 2.0)
        sr = math.sin(self.roll_rad / 2.0)
        cp = math.cos(self.pitch_rad / 2.0)
        sp = math.sin(self.pitch_rad / 2.0)
        return cp * cr, cp * sr, sp * cr, -sp * sr


POSE_CASES = {
    "separated": PoseCase("separated", origin_z_m=-0.005),
    "aligned": PoseCase("aligned", origin_z_m=0.0),
    "x_offset_pos_100um": PoseCase(
        "x_offset_pos_100um", origin_z_m=0.0, x_offset_m=0.0001
    ),
    "combined_a": PoseCase(
        "combined_a",
        origin_z_m=0.0,
        x_offset_m=0.00006,
        y_offset_m=-0.00004,
        roll_rad=math.radians(1.5),
        pitch_rad=math.radians(-1.5),
    ),
}


def find_project_root(start: Path) -> Path:
    """Find the repository root without depending on the process CWD."""

    resolved = Path(start).resolve()
    if resolved.is_file():
        resolved = resolved.parent
    for candidate in (resolved, *resolved.parents):
        if (candidate / "pyproject.toml").is_file() and (
            candidate / FORMAL_MODEL
        ).is_file():
            return candidate
    raise FileNotFoundError(
        "无法定位项目根目录：未同时找到 pyproject.toml 和正式模型 models/dsub9_pair.xml。"
    )


@contextmanager
def project_root_cwd(root: Path = PROJECT_ROOT) -> Iterator[None]:
    """Temporarily use the root required by MuJoCo's Windows plugin loader."""

    previous = Path.cwd()
    os.chdir(root)
    try:
        yield
    finally:
        os.chdir(previous)


@functools.lru_cache(maxsize=1)
def _register_sdf_plugin() -> None:
    plugin = PROJECT_ROOT / PLUGIN_RELATIVE_PATH
    if not plugin.is_file():
        raise FileNotFoundError(
            f"正式 SDF 插件不存在：{plugin}。请先按项目说明编译 Release 版 DLL。"
        )
    with project_root_cwd():
        mujoco.mj_loadPluginLibrary(PLUGIN_RELATIVE_PATH.as_posix())


def load_model(mode: CollisionMode) -> mujoco.MjModel:
    """Compile one reviewed model without changing its physical parameters."""

    if mode == "sdf":
        _register_sdf_plugin()
        relative = FORMAL_MODEL
    elif mode == "polygon32":
        relative = FALLBACK_MODEL
    else:
        raise ValueError("模型类型必须是 'sdf' 或 'polygon32'。")

    path = PROJECT_ROOT / relative
    if not path.is_file():
        raise FileNotFoundError(f"模型文件不存在：{path}")
    with project_root_cwd():
        return mujoco.MjModel.from_xml_path(relative.as_posix())


def apply_pose(model: mujoco.MjModel, data: mujoco.MjData, pose: PoseCase) -> None:
    """Reset data, prescribe the male free-joint pose, and call mj_forward only."""

    if model.nq < 7:
        raise ValueError("模型缺少公头所需的 7 自由度 free joint。")
    mujoco.mj_resetData(model, data)
    data.qpos[:3] = (pose.x_offset_m, pose.y_offset_m, pose.origin_z_m)
    data.qpos[3:7] = pose.quaternion_wxyz()
    mujoco.mj_forward(model, data)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def input_hashes() -> dict[str, str]:
    """Hash reviewed inputs that visualization generation must not overwrite."""

    paths = [
        PROJECT_ROOT / FORMAL_MODEL,
        PROJECT_ROOT / CONTACT_RESULTS,
        *(PROJECT_ROOT / "models" / "includes").glob("*"),
        *(PROJECT_ROOT / "assets" / "collision").rglob("*"),
    ]
    fallback = PROJECT_ROOT / FALLBACK_MODEL
    if fallback.is_file():
        paths.append(fallback)
    files = sorted(path for path in paths if path.is_file())
    return {
        path.relative_to(PROJECT_ROOT).as_posix(): _sha256(path) for path in files
    }

