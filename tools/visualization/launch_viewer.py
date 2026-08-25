"""Preflight and launch the reviewed D-sub9 models in MuJoCo viewer."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time
from typing import Sequence

import mujoco
import mujoco.viewer

from tools.model.generate_mjcf import generate_model
from tools.visualization.runtime import (
    CollisionMode,
    FALLBACK_MODEL,
    FORMAL_MODEL,
    PLUGIN_RELATIVE_PATH,
    POSE_CASES,
    PROJECT_ROOT,
    apply_pose,
    load_model,
)


def check_required_files(mode: CollisionMode, root: Path = PROJECT_ROOT) -> list[str]:
    """Return actionable Chinese preflight errors without loading MuJoCo."""

    project = Path(root)
    issues: list[str] = []
    if not (project / "pyproject.toml").is_file():
        issues.append(f"项目标识文件不存在：{project / 'pyproject.toml'}")
    if mode == "sdf":
        if not (project / FORMAL_MODEL).is_file():
            issues.append(f"正式 SDF 模型不存在：{project / FORMAL_MODEL}")
        if not (project / PLUGIN_RELATIVE_PATH).is_file():
            issues.append(
                f"正式 SDF 插件不存在：{project / PLUGIN_RELATIVE_PATH}。"
                "请先编译 Release 版插件。"
            )
    elif mode == "polygon32":
        generator = project / "tools/model/generate_mjcf.py"
        if not (project / FALLBACK_MODEL).is_file() and not generator.is_file():
            issues.append(
                f"免插件模型和生成器均不存在：{project / FALLBACK_MODEL}；{generator}"
            )
    else:
        issues.append("模型类型必须是 sdf 或 polygon32。")

    for relative in (
        Path("models/includes/dsub9_visual.xml"),
        Path("models/includes/dsub9_collision.xml"),
        Path("assets/visual/dsub9_female_visual_centered.stl"),
        Path("assets/visual/dsub9_male_visual_centered.stl"),
        Path("assets/collision"),
    ):
        if not (project / relative).exists():
            issues.append(f"模型所需资产不存在：{project / relative}")
    return issues


def ensure_fallback_model(root: Path = PROJECT_ROOT) -> Path:
    """Generate the reviewed polygon32 XML only when it is absent."""

    output = Path(root) / FALLBACK_MODEL
    if output.is_file():
        return output
    if Path(root).resolve() != PROJECT_ROOT.resolve():
        raise FileNotFoundError(f"回退模型不存在，且测试根目录不允许自动生成：{output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    generate_model("polygon32", output)
    return output


def _validate_compiled_model(model: mujoco.MjModel, mode: CollisionMode) -> None:
    names = (
        "female_visual",
        "male_visual",
        "pin_01",
        "pin_09",
        "d_socket_female_seg_000",
        "d_guide_male_seg_000",
        "hole_sdf_01" if mode == "sdf" else "hole_fallback_32_h01_entry_s00",
    )
    missing = [
        name
        for name in names
        if mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, name) < 0
    ]
    if missing:
        raise RuntimeError(f"模型编译后缺少关键几何体：{', '.join(missing)}")


def _success_message(mode: CollisionMode) -> str:
    if mode == "sdf":
        return "正式 SDF 模型检查通过（解析圆孔插件已加载）。"
    return "免插件 polygon32 模型检查通过（该模型是近似回退模型）。"


def _print_error(error: Exception) -> None:
    print("\n启动失败。", file=sys.stderr)
    print(f"原因：{error}", file=sys.stderr)
    print(
        "建议：确认使用 D:\\KEYANRUJIAN\\python.exe，并保持项目目录、build、models 和 assets 完整。",
        file=sys.stderr,
    )


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="打开 D-sub9 MuJoCo 场景。")
    parser.add_argument("--mode", choices=("sdf", "polygon32"), required=True)
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="只检查依赖和模型编译，不打开窗口",
    )
    args = parser.parse_args(argv)
    mode: CollisionMode = args.mode

    try:
        if mode == "polygon32":
            ensure_fallback_model()
        issues = check_required_files(mode)
        if issues:
            raise FileNotFoundError("\n".join(issues))
        model = load_model(mode)
        _validate_compiled_model(model, mode)
        print(_success_message(mode))
        if args.check_only:
            return 0

        data = mujoco.MjData(model)
        apply_pose(model, data, POSE_CASES["aligned"])
        print("正在打开 MuJoCo viewer；关闭窗口即可退出。")
        with mujoco.viewer.launch_passive(model, data) as viewer:
            viewer.opt.geomgroup[:] = 0
            viewer.opt.geomgroup[2] = 1
            while viewer.is_running():
                viewer.sync()
                time.sleep(0.02)
        return 0
    except Exception as error:
        _print_error(error)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
