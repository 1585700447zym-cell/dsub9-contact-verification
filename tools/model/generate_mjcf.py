"""Generate the formal SDF and polygon32 fallback D-sub9 pair models."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Literal


CollisionMode = Literal["sdf", "polygon32"]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSET_DIR = PROJECT_ROOT / "assets"
MODEL_DIR = PROJECT_ROOT / "models"
INCLUDE_DIR = MODEL_DIR / "includes"

PIN_CENTRES_M: tuple[tuple[float, float], ...] = (
    (-0.00554, 0.00142),
    (-0.00277, 0.00142),
    (0.0, 0.00142),
    (0.00277, 0.00142),
    (0.00554, 0.00142),
    (-0.004155, -0.00142),
    (-0.001385, -0.00142),
    (0.001385, -0.00142),
    (0.004155, -0.00142),
)

SDF_CONFIG: tuple[tuple[str, str], ...] = (
    ("bore_radius", "0.000575"),
    ("entry_radius", "0.000675"),
    ("entry_depth", "0.00025"),
    ("bore_depth", "0.00450"),
    ("outer_radius", "0.00100"),
)

MALE_GUIDE_NAMES = tuple(f"d_guide_male_seg_{index:03d}" for index in range(78))
FEMALE_SOCKET_NAMES = tuple(f"d_socket_female_seg_{index:03d}" for index in range(42))
FALLBACK_NAMES = tuple(
    f"hole_fallback_32_h{hole:02d}_{layer}_s{sector:02d}"
    for hole in range(1, 10)
    for layer in ("entry", "main")
    for sector in range(32)
)


def pin_centres_m() -> tuple[tuple[float, float], ...]:
    """Return the nine documented pin/hole centres in metres."""
    return PIN_CENTRES_M


def _coordinate(value: float) -> str:
    if value == 0.0:
        return "0"
    return format(value, ".9g")


def _asset_path(name: str) -> Path:
    return ASSET_DIR / "collision" / f"{name}.stl"


def _require_assets() -> None:
    required = (
        ASSET_DIR / "visual" / "dsub9_female_visual_centered.stl",
        ASSET_DIR / "visual" / "dsub9_male_visual_centered.stl",
        *(_asset_path(name) for name in MALE_GUIDE_NAMES),
        *(_asset_path(name) for name in FEMALE_SOCKET_NAMES),
        *(_asset_path(name) for name in FALLBACK_NAMES),
    )
    missing = [path.relative_to(PROJECT_ROOT).as_posix() for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("missing reviewed collision assets: " + ", ".join(missing))


def _visual_include_xml() -> str:
    return """<mujoco>
  <asset>
    <mesh name="dsub9_female_visual" file="visual/dsub9_female_visual_centered.stl" scale="0.001 0.001 0.001"/>
    <mesh name="dsub9_male_visual" file="visual/dsub9_male_visual_centered.stl" scale="0.001 0.001 0.001"/>
  </asset>
</mujoco>
"""


def _collision_include_xml() -> str:
    lines = ["<mujoco>", "  <asset>"]
    for name in (*MALE_GUIDE_NAMES, *FEMALE_SOCKET_NAMES):
        lines.append(
            f'    <mesh name="{name}" file="collision/{name}.stl" scale="0.001 0.001 0.001"/>'
        )
    lines.extend(("  </asset>", "</mujoco>"))
    return "\n".join(lines) + "\n"


def _defaults_xml() -> list[str]:
    return [
        "  <default>",
        "    <default class=\"visual\">",
        "      <geom contype=\"0\" conaffinity=\"0\" group=\"2\"/>",
        "    </default>",
        "    <default class=\"pin_collision\">",
        "      <geom contype=\"1\" conaffinity=\"2\"/>",
        "    </default>",
        "    <default class=\"hole_sdf_collision\">",
        "      <geom contype=\"2\" conaffinity=\"1\"/>",
        "    </default>",
        "    <default class=\"male_guide_collision\">",
        "      <geom contype=\"4\" conaffinity=\"8\"/>",
        "    </default>",
        "    <default class=\"female_socket_collision\">",
        "      <geom contype=\"8\" conaffinity=\"4\"/>",
        "    </default>",
        "    <default class=\"hole_polygon32_collision\">",
        "      <geom contype=\"2\" conaffinity=\"1\"/>",
        "    </default>",
        "  </default>",
    ]


def _sdf_extension_xml() -> list[str]:
    lines = [
        "  <extension>",
        "    <plugin plugin=\"mujoco.sdf.dsub9_hole\">",
        "      <instance name=\"hole_sdf\">",
    ]
    lines.extend(f'        <config key="{key}" value="{value}"/>' for key, value in SDF_CONFIG)
    lines.extend(
        (
            "      </instance>",
            "    </plugin>",
            "  </extension>",
        )
    )
    return lines


def _include_xml(collision_mode: CollisionMode) -> list[str]:
    prefix = "includes" if collision_mode == "sdf" else "../models/includes"
    return [
        f'  <include file="{prefix}/dsub9_visual.xml"/>',
        f'  <include file="{prefix}/dsub9_collision.xml"/>',
    ]


def _mode_asset_xml(collision_mode: CollisionMode) -> list[str]:
    if collision_mode == "sdf":
        return [
            "  <asset>",
            "    <mesh name=\"hole_sdf_mesh\">",
            "      <plugin instance=\"hole_sdf\"/>",
            "    </mesh>",
            "  </asset>",
        ]
    lines = ["  <asset>"]
    lines.extend(
        f'    <mesh name="{name}" file="collision/{name}.stl" scale="0.001 0.001 0.001"/>'
        for name in FALLBACK_NAMES
    )
    lines.append("  </asset>")
    return lines


def _female_body_xml(collision_mode: CollisionMode) -> list[str]:
    lines = [
        "    <body name=\"female\">",
        "      <geom name=\"female_visual\" class=\"visual\" type=\"mesh\" mesh=\"dsub9_female_visual\" group=\"2\" contype=\"0\" conaffinity=\"0\"/>",
    ]
    lines.extend(
        f'      <geom name="{name}" class="female_socket_collision" type="mesh" mesh="{name}"/>'
        for name in FEMALE_SOCKET_NAMES
    )
    if collision_mode == "sdf":
        for index, (x, y) in enumerate(PIN_CENTRES_M, start=1):
            lines.extend(
                (
                    f'      <geom name="hole_sdf_{index:02d}" class="hole_sdf_collision" type="sdf" mesh="hole_sdf_mesh" pos="{_coordinate(x)} {_coordinate(y)} 0">',
                    "        <plugin instance=\"hole_sdf\"/>",
                    "      </geom>",
                )
            )
    else:
        lines.extend(
            f'      <geom name="{name}" class="hole_polygon32_collision" type="mesh" mesh="{name}"/>'
            for name in FALLBACK_NAMES
        )
    lines.append("    </body>")
    return lines


def _male_body_xml() -> list[str]:
    lines = [
        "    <body name=\"male\">",
        "      <inertial pos=\"0 0 0\" mass=\"0.05\" diaginertia=\"0.00002 0.00002 0.00002\"/>",
        "      <freejoint name=\"male_freejoint\"/>",
        "      <geom name=\"male_visual\" class=\"visual\" type=\"mesh\" mesh=\"dsub9_male_visual\" group=\"2\" contype=\"0\" conaffinity=\"0\"/>",
    ]
    lines.extend(
        f'      <geom name="{name}" class="male_guide_collision" type="mesh" mesh="{name}"/>'
        for name in MALE_GUIDE_NAMES
    )
    for index, (x, y) in enumerate(PIN_CENTRES_M, start=1):
        lines.append(
            f'      <geom name="pin_{index:02d}" class="pin_collision" type="cylinder" size="0.0005 0.002" pos="{_coordinate(x)} {_coordinate(y)} 0.002"/>'
        )
    lines.append("    </body>")
    return lines


def build_pair_xml(collision_mode: CollisionMode) -> str:
    """Return deterministic MJCF for the formal SDF or polygon32 fallback model."""
    if collision_mode not in ("sdf", "polygon32"):
        raise ValueError("collision_mode must be 'sdf' or 'polygon32'")
    model_name = "dsub9_pair_sdf" if collision_mode == "sdf" else "dsub9_pair_polygon32_fallback"
    lines = [
        f'<mujoco model="{model_name}">',
        "  <compiler angle=\"radian\" meshdir=\"../assets\"/>",
        "  <option gravity=\"0 0 0\"/>",
        *_defaults_xml(),
    ]
    if collision_mode == "sdf":
        lines.extend(_sdf_extension_xml())
    lines.extend(_include_xml(collision_mode))
    lines.extend(_mode_asset_xml(collision_mode))
    lines.extend(("  <worldbody>", *_female_body_xml(collision_mode), *_male_body_xml(), "  </worldbody>"))
    lines.append("</mujoco>")
    return "\n".join(lines) + "\n"


def _write_includes() -> None:
    INCLUDE_DIR.mkdir(parents=True, exist_ok=True)
    (INCLUDE_DIR / "dsub9_visual.xml").write_text(_visual_include_xml(), encoding="utf-8")
    (INCLUDE_DIR / "dsub9_collision.xml").write_text(
        _collision_include_xml(), encoding="utf-8"
    )


def generate_model(collision_mode: CollisionMode, output: Path) -> Path:
    """Validate assets, maintain includes, and write one deterministic model."""
    _require_assets()
    _write_includes()
    target = output if output.is_absolute() else PROJECT_ROOT / output
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(build_pair_xml(collision_mode), encoding="utf-8")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collision-mode", choices=("sdf", "polygon32"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    target = generate_model(args.collision_mode, args.output)
    print(f"generated {args.collision_mode} model: {target}")


if __name__ == "__main__":
    main()
