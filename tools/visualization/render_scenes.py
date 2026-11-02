"""Render six annotated D-sub9 scene screenshots without changing physics."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import textwrap
from typing import Literal, Sequence

import mujoco
import numpy as np
from PIL import Image, ImageDraw, ImageFont, PngImagePlugin

from tools.visualization.font_support import find_chinese_font
from tools.visualization.runtime import (
    CollisionMode,
    POSE_CASES,
    PROJECT_ROOT,
    PoseCase,
    apply_pose,
    load_model,
)


DisplayMode = Literal["visual", "collision_overlay", "collision"]
GENERATION_METHOD = "MuJoCo offscreen + Pillow annotation"
OUTPUT_SIZE = (1600, 900)
RAW_HEIGHT = 760


@dataclass(frozen=True)
class CameraPreset:
    lookat: tuple[float, float, float]
    distance: float
    azimuth: float
    elevation: float

    def build(self) -> mujoco.MjvCamera:
        camera = mujoco.MjvCamera()
        camera.type = mujoco.mjtCamera.mjCAMERA_FREE
        camera.lookat[:] = self.lookat
        camera.distance = self.distance
        camera.azimuth = self.azimuth
        camera.elevation = self.elevation
        return camera


CAMERAS = {
    "overview": CameraPreset((0.0, 0.0, -0.0005), 0.043, 125.0, -22.0),
    "overlay": CameraPreset((0.0, 0.0, 0.0005), 0.031, 135.0, -28.0),
    "array": CameraPreset((0.0, 0.0, 0.0005), 0.024, 90.0, -88.0),
}


def _geom_name(model: mujoco.MjModel, index: int) -> str:
    return mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, index) or ""


def style_model_for_display(model: mujoco.MjModel, display: DisplayMode) -> None:
    """Change only runtime RGBA values so collision roles are easy to see."""

    if display == "visual":
        return
    if display not in ("collision_overlay", "collision"):
        raise ValueError(f"未知显示模式：{display}")

    for index in range(model.ngeom):
        name = _geom_name(model, index)
        if name.endswith("_visual"):
            alpha = 0.20 if display == "collision_overlay" else 0.03
            model.geom_rgba[index] = (0.72, 0.76, 0.82, alpha)
        elif name.startswith("pin_"):
            model.geom_rgba[index] = (1.0, 0.48, 0.05, 0.96)
        elif name.startswith("hole_"):
            model.geom_rgba[index] = (0.05, 0.55, 0.95, 0.86)
        elif name.startswith("d_guide_male_"):
            model.geom_rgba[index] = (0.12, 0.78, 0.38, 0.76)
        elif name.startswith("d_socket_female_"):
            model.geom_rgba[index] = (0.86, 0.20, 0.67, 0.76)


def _scene_option(display: DisplayMode) -> mujoco.MjvOption:
    option = mujoco.MjvOption()
    option.geomgroup[:] = 0
    if display == "visual":
        option.geomgroup[2] = 1
    elif display == "collision_overlay":
        option.geomgroup[0] = 1
        option.geomgroup[2] = 1
        option.flags[mujoco.mjtVisFlag.mjVIS_TRANSPARENT] = 1
    else:
        option.geomgroup[0] = 1
    option.flags[mujoco.mjtVisFlag.mjVIS_STATIC] = 1
    return option


def render_frame(
    mode: CollisionMode,
    pose: PoseCase,
    camera: CameraPreset,
    display: DisplayMode,
    *,
    width: int = 1600,
    height: int = RAW_HEIGHT,
) -> Image.Image:
    """Render one prescribed pose with deterministic camera and display groups."""

    model = load_model(mode)
    style_model_for_display(model, display)
    model.vis.global_.offwidth = max(model.vis.global_.offwidth, width)
    model.vis.global_.offheight = max(model.vis.global_.offheight, height)
    model.vis.headlight.ambient[:] = (0.45, 0.45, 0.45)
    model.vis.headlight.diffuse[:] = (0.70, 0.70, 0.70)
    data = mujoco.MjData(model)
    apply_pose(model, data, pose)

    renderer = mujoco.Renderer(model, height=height, width=width)
    try:
        renderer.update_scene(data, camera=camera.build(), scene_option=_scene_option(display))
        pixels = np.asarray(renderer.render()).copy()
    finally:
        renderer.close()
    return Image.fromarray(pixels, mode="RGB")


def _fit_font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(find_chinese_font()), size=size)


def annotate_image(
    raw: Image.Image,
    title: str,
    caption: str,
    *,
    panel_labels: tuple[str, str] | None = None,
    insertion_arrow: bool = False,
) -> Image.Image:
    """Add fixed Chinese title/caption bands while preserving 1600×900 output."""

    canvas = Image.new("RGB", OUTPUT_SIZE, "#F6F8FA")
    fitted = raw.convert("RGB").resize((1600, RAW_HEIGHT), Image.Resampling.LANCZOS)
    canvas.paste(fitted, (0, 70))
    draw = ImageDraw.Draw(canvas)
    title_font = _fit_font(32)
    caption_font = _fit_font(21)
    label_font = _fit_font(22)
    title_box = draw.textbbox((0, 0), title, font=title_font)
    draw.text(
        ((1600 - (title_box[2] - title_box[0])) / 2, 17),
        title,
        fill="#172B4D",
        font=title_font,
    )
    wrapped = "\n".join(textwrap.wrap(caption, width=68))
    draw.multiline_text(
        (800, 842),
        wrapped,
        fill="#4A5568",
        font=caption_font,
        anchor="mm",
        align="center",
        spacing=3,
    )
    if panel_labels:
        draw.rounded_rectangle((20, 82, 430, 126), radius=8, fill="#FFFFFFDD")
        draw.text((35, 89), panel_labels[0], fill="#0B4F8A", font=label_font)
        draw.rounded_rectangle((820, 82, 1575, 126), radius=8, fill="#FFFFFFDD")
        draw.text((835, 89), panel_labels[1], fill="#7A2E0E", font=label_font)
    if insertion_arrow:
        arrow_color = "#F2C94C"
        draw.line((1325, 665, 1325, 430), fill=arrow_color, width=12)
        draw.polygon(((1325, 390), (1295, 445), (1355, 445)), fill=arrow_color)
        draw.rounded_rectangle((1125, 675, 1515, 724), radius=8, fill="#172B4DDD")
        draw.text((1145, 685), "+Z 插入方向", fill="white", font=label_font)
    return canvas


def _save_png(
    image: Image.Image,
    path: Path,
    *,
    title: str,
    caption: str,
    model_mode: str,
    extra_metadata: dict[str, str] | None = None,
) -> Path:
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("Title", title)
    metadata.add_text("Caption", caption)
    metadata.add_text("ModelMode", model_mode)
    metadata.add_text("GenerationMethod", GENERATION_METHOD)
    for key, value in (extra_metadata or {}).items():
        metadata.add_text(key, value)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", pnginfo=metadata, optimize=True)
    return path


def _render_annotated(
    output: Path,
    *,
    mode: CollisionMode,
    pose: PoseCase,
    camera: CameraPreset,
    display: DisplayMode,
    title: str,
    caption: str,
    insertion_arrow: bool = False,
) -> Path:
    raw = render_frame(mode, pose, camera, display)
    return _save_png(
        annotate_image(raw, title, caption, insertion_arrow=insertion_arrow),
        output,
        title=title,
        caption=caption,
        model_mode=mode,
        extra_metadata=(
            {"InsertionDirection": "+world/task Z"} if insertion_arrow else None
        ),
    )


def generate_screenshots(output_dir: Path) -> list[Path]:
    """Generate the exact six screenshots required by the delivery package."""

    output = Path(output_dir)
    aligned_overview = PoseCase("aligned_overview", origin_z_m=-0.004)
    outputs = [
        _render_annotated(
            output / "01_对齐场景总览.png",
            mode="sdf",
            pose=aligned_overview,
            camera=CAMERAS["overview"],
            display="visual",
            title="D-sub9 对齐场景总览",
            caption="公头无横向与角度误差，沿世界坐标 +Z 方向接近母头；保留间距以便观察公母头。",
            insertion_arrow=True,
        ),
        _render_annotated(
            output / "02_碰撞几何叠加.png",
            mode="sdf",
            pose=POSE_CASES["aligned"],
            camera=CAMERAS["overlay"],
            display="collision_overlay",
            title="视觉模型与碰撞几何叠加",
            caption="橙色为公针、蓝色为解析孔、绿色为公头导向、紫色为母头插座；半透明外壳仅用于显示。",
        ),
        _render_annotated(
            output / "03_九针九孔局部放大.png",
            mode="sdf",
            pose=POSE_CASES["aligned"],
            camera=CAMERAS["array"],
            display="collision",
            title="9 针—9 孔局部关系（5+4 阵列）",
            caption="正视局部碰撞几何：橙色圆柱为 9 根公针，蓝色解析几何对应 9 个母孔。",
        ),
        _render_annotated(
            output / "04_正X偏移100微米.png",
            mode="sdf",
            pose=POSE_CASES["x_offset_pos_100um"],
            camera=CAMERAS["array"],
            display="collision_overlay",
            title="正 X 偏移 100 微米规定姿态",
            caption="公头整体沿 +X 偏移 0.0001 m；这是规定姿态的几何展示，不是自由动力学结果。",
        ),
        _render_annotated(
            output / "05_组合偏差工况A.png",
            mode="sdf",
            pose=POSE_CASES["combined_a"],
            camera=CAMERAS["overlay"],
            display="collision_overlay",
            title="组合偏差工况 A",
            caption="规定偏差：X=+60 微米、Y=-40 微米、滚转=+1.5°、俯仰=-1.5°；未运行自由动力学。",
        ),
    ]

    left = render_frame(
        "sdf", POSE_CASES["aligned"], CAMERAS["array"], "collision", width=800
    )
    right = render_frame(
        "polygon32",
        POSE_CASES["aligned"],
        CAMERAS["array"],
        "collision",
        width=800,
    )
    comparison_raw = Image.new("RGB", (1600, RAW_HEIGHT), "white")
    comparison_raw.paste(left, (0, 0))
    comparison_raw.paste(right, (800, 0))
    comparison_title = "正式解析 SDF 与 polygon32 回退模型对照"
    comparison_caption = (
        "相同相机与规定姿态。左侧是正式解析圆孔；右侧 polygon32 是扇区网格近似，仅用于快速查看和对照。"
    )
    comparison = annotate_image(
        comparison_raw,
        comparison_title,
        comparison_caption,
        panel_labels=("左：正式解析 SDF", "右：polygon32 近似回退模型（非解析圆孔）"),
    )
    outputs.append(
        _save_png(
            comparison,
            output / "06_正式SDF与回退模型对照.png",
            title=comparison_title,
            caption=comparison_caption,
            model_mode="sdf+polygon32",
        )
    )
    return outputs


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成 D-sub9 六张中文场景截图。")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "deliverables/chinese_visual_package/screenshots",
    )
    args = parser.parse_args(argv)
    for path in generate_screenshots(args.output_dir):
        print(f"已生成：{path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
