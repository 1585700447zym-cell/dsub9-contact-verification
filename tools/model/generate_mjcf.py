"""Generate the formal SDF and polygon32 fallback D-sub9 pair models."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import math
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


@dataclass(frozen=True)
class ContactParameters:
    """Uncalibrated diagnostic contact parameters for MuJoCo geoms.

    ``friction`` has three MuJoCo coefficients (sliding, torsional, rolling),
    ``solref`` is ``(time_constant_s, damping_ratio)``, ``solimp`` is
    ``(d0, d_width, width_m, midpoint, power)``, and ``margin_m`` is metres.
    The fixed tuple shapes match MJCF's geom attribute schema.
    """

    name: str
    friction: tuple[float, float, float]
    solref: tuple[float, float]
    solimp: tuple[float, float, float, float, float]
    margin_m: float

    def __post_init__(self) -> None:
        shaped_values = (
            ("friction", self.friction, 3),
            ("solref", self.solref, 2),
            ("solimp", self.solimp, 5),
        )
        if not self.name:
            raise ValueError("contact parameter name must be non-empty")
        for field_name, values, expected_length in shaped_values:
            if not isinstance(values, tuple) or len(values) != expected_length:
                raise ValueError(f"{field_name} must be a {expected_length}-tuple")
        numeric_values = (*self.friction, *self.solref, *self.solimp, self.margin_m)
        if not all(math.isfinite(value) for value in numeric_values):
            raise ValueError("contact parameters must be finite")
        if any(value < 0.0 for value in self.friction) or self.margin_m < 0.0:
            raise ValueError("friction and margin must be non-negative")
        if any(value <= 0.0 for value in self.solref):
            raise ValueError("solref values must be positive")


_UNCALIBRATED_DIAGNOSTIC_V1 = ContactParameters(
    name="uncalibrated_diagnostic_v1",
    friction=(1.0, 0.005, 0.0001),
    solref=(0.02, 1.0),
    solimp=(0.9, 0.95, 0.001, 0.5, 2.0),
    margin_m=0.0,
)


def baseline_contact_parameters() -> ContactParameters:
    """Return the versioned, uncalibrated diagnostic contact baseline."""
    return _UNCALIBRATED_DIAGNOSTIC_V1


def _mjcf_number(value: float) -> str:
    text = f"{value:.15f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def contact_parameters_mjcf(parameters: ContactParameters) -> dict[str, str]:
    """Format one contact configuration as deterministic MJCF geom attributes."""
    if not isinstance(parameters, ContactParameters):
        raise TypeError("parameters must be ContactParameters")
    return {
        "friction": " ".join(_mjcf_number(value) for value in parameters.friction),
        "solref": " ".join(_mjcf_number(value) for value in parameters.solref),
        "solimp": " ".join(_mjcf_number(value) for value in parameters.solimp),
        "margin": _mjcf_number(parameters.margin_m),
    }


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


def _defaults_xml(contact_parameters: ContactParameters) -> list[str]:
    contact_attributes = " ".join(
        f'{name}="{value}"' for name, value in contact_parameters_mjcf(contact_parameters).items()
    )
    return [
        "  <default>",
        "    <default class=\"visual\">",
        "      <geom contype=\"0\" conaffinity=\"0\" group=\"2\"/>",
        "    </default>",
        "    <default class=\"pin_collision\">",
        f"      <geom contype=\"1\" conaffinity=\"2\" {contact_attributes}/>",
        "    </default>",
        "    <default class=\"hole_sdf_collision\">",
        f"      <geom contype=\"2\" conaffinity=\"1\" {contact_attributes}/>",
        "    </default>",
        "    <default class=\"male_guide_collision\">",
        f"      <geom contype=\"4\" conaffinity=\"8\" {contact_attributes}/>",
        "    </default>",
        "    <default class=\"female_socket_collision\">",
        f"      <geom contype=\"8\" conaffinity=\"4\" {contact_attributes}/>",
        "    </default>",
        "    <default class=\"hole_polygon32_collision\">",
        f"      <geom contype=\"2\" conaffinity=\"1\" {contact_attributes}/>",
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


def build_pair_xml(
    collision_mode: CollisionMode,
    *,
    contact_parameters: ContactParameters | None = None,
) -> str:
    """Return deterministic MJCF for the formal SDF or polygon32 fallback model."""
    if collision_mode not in ("sdf", "polygon32"):
        raise ValueError("collision_mode must be 'sdf' or 'polygon32'")
    if contact_parameters is None:
        contact_parameters = baseline_contact_parameters()
    model_name = "dsub9_pair_sdf" if collision_mode == "sdf" else "dsub9_pair_polygon32_fallback"
    lines = [
        f'<mujoco model="{model_name}">',
        "  <compiler angle=\"radian\" meshdir=\"../assets\"/>",
        "  <option gravity=\"0 0 0\"/>",
        (
            "  <!-- UNCALIBRATED diagnostic contact baseline: "
            f"{contact_parameters.name}; not material-identified. -->"
        ),
        *_defaults_xml(contact_parameters),
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
    _write_text_lf(INCLUDE_DIR / "dsub9_visual.xml", _visual_include_xml())
    _write_text_lf(INCLUDE_DIR / "dsub9_collision.xml", _collision_include_xml())


def _write_text_lf(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


def generate_model(collision_mode: CollisionMode, output: Path) -> Path:
    """Validate assets, maintain includes, and write one deterministic model."""
    _require_assets()
    _write_includes()
    target = output if output.is_absolute() else PROJECT_ROOT / output
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_text_lf(target, build_pair_xml(collision_mode))
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
