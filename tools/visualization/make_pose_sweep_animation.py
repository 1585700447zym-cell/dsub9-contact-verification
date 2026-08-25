"""Create an explicitly quasi-static prescribed-pose D-sub9 GIF."""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
from typing import Sequence

import mujoco
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from tools.visualization.font_support import find_chinese_font
from tools.visualization.render_scenes import (
    CAMERAS,
    _scene_option,
    style_model_for_display,
)
from tools.visualization.runtime import (
    POSE_CASES,
    PROJECT_ROOT,
    PoseCase,
    apply_pose,
    load_model,
)


DISCLAIMER = "准静态规定姿态扫描演示；不是自由动力学插入，不包含机器人或力控制器。"
DEFAULT_SIZE = (960, 540)


def _interpolate(start: PoseCase, end: PoseCase, fraction: float, name: str) -> PoseCase:
    def mix(left: float, right: float) -> float:
        return left + (right - left) * fraction

    return PoseCase(
        name=name,
        origin_z_m=mix(start.origin_z_m, end.origin_z_m),
        x_offset_m=mix(start.x_offset_m, end.x_offset_m),
        y_offset_m=mix(start.y_offset_m, end.y_offset_m),
        roll_rad=mix(start.roll_rad, end.roll_rad),
        pitch_rad=mix(start.pitch_rad, end.pitch_rad),
    )


def _transition(
    start: PoseCase, end: PoseCase, count: int, name: str
) -> list[PoseCase]:
    if count < 2:
        raise ValueError("过渡段至少需要 2 帧。")
    return [
        _interpolate(start, end, index / (count - 1), name)
        for index in range(count)
    ]


def build_pose_sequence(fps: int = 10) -> list[PoseCase]:
    """Return a deterministic twelve-second prescribed-pose sequence."""

    if fps < 2:
        raise ValueError("动画帧率至少为 2 fps。")
    separated = POSE_CASES["separated"]
    aligned = POSE_CASES["aligned"]
    x_offset = POSE_CASES["x_offset_pos_100um"]
    combined = replace(POSE_CASES["combined_a"], name="组合偏差 A")
    return [
        *_transition(separated, aligned, 5 * fps, "沿 +Z 准静态接近"),
        *[PoseCase("对齐姿态", origin_z_m=0.0) for _ in range(2 * fps)],
        *[
            PoseCase("+X 偏移 100 微米", origin_z_m=0.0, x_offset_m=0.0001)
            for _ in range(2 * fps)
        ],
        *_transition(x_offset, combined, 2 * fps, "过渡至组合偏差 A"),
        *[combined for _ in range(fps)],
    ]


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(find_chinese_font()), size=size)


def _annotate_frame(
    raw: Image.Image,
    pose: PoseCase,
    size: tuple[int, int],
    *,
    frame_index: int,
    frame_count: int,
    fps: int,
) -> Image.Image:
    width, height = size
    top = max(34, height // 12)
    bottom = max(42, height // 11)
    canvas = Image.new("RGB", size, "#F6F8FA")
    canvas.paste(
        raw.resize((width, height - top - bottom), Image.Resampling.LANCZOS),
        (0, top),
    )
    draw = ImageDraw.Draw(canvas)
    title_font = _font(max(15, width // 38))
    disclaimer_font = _font(max(10, width // 58))
    title = f"D-sub9 准静态位姿扫描｜{pose.name}｜t={frame_index / fps:.1f} s"
    title_box = draw.textbbox((0, 0), title, font=title_font)
    draw.text(
        ((width - (title_box[2] - title_box[0])) / 2, max(5, top // 5)),
        title,
        fill="#172B4D",
        font=title_font,
    )
    draw.rectangle((0, height - bottom, width, height), fill="#8B1E1E")
    progress = (frame_index + 1) / frame_count
    draw.rectangle((0, height - bottom, round(width * progress), height - bottom + 5), fill="#F2C94C")
    draw.text(
        (width / 2, height - bottom / 2),
        DISCLAIMER,
        fill="white",
        font=disclaimer_font,
        anchor="mm",
    )
    return canvas


def make_animation(
    output: Path,
    *,
    fps: int = 10,
    size: tuple[int, int] = DEFAULT_SIZE,
) -> Path:
    """Render and save the prescribed sequence; no dynamics step is performed."""

    width, height = size
    if width < 320 or height < 180:
        raise ValueError("动画分辨率至少为 320×180。")
    poses = build_pose_sequence(fps)
    top = max(34, height // 12)
    bottom = max(42, height // 11)
    raw_height = height - top - bottom

    model = load_model("sdf")
    style_model_for_display(model, "collision_overlay")
    model.vis.global_.offwidth = max(model.vis.global_.offwidth, width)
    model.vis.global_.offheight = max(model.vis.global_.offheight, raw_height)
    model.vis.headlight.ambient[:] = (0.45, 0.45, 0.45)
    model.vis.headlight.diffuse[:] = (0.70, 0.70, 0.70)
    data = mujoco.MjData(model)
    option = _scene_option("collision_overlay")
    camera = CAMERAS["overlay"].build()
    frames: list[Image.Image] = []

    renderer = mujoco.Renderer(model, height=raw_height, width=width)
    try:
        for frame_index, pose in enumerate(poses):
            apply_pose(model, data, pose)
            renderer.update_scene(data, camera=camera, scene_option=option)
            pixels = np.asarray(renderer.render()).copy()
            frames.append(
                _annotate_frame(
                    Image.fromarray(pixels, mode="RGB"),
                    pose,
                    size,
                    frame_index=frame_index,
                    frame_count=len(poses),
                    fps=fps,
                )
            )
    finally:
        renderer.close()

    first = frames[0].convert("P", palette=Image.Palette.ADAPTIVE, colors=128)
    indexed = [first]
    indexed.extend(
        frame.quantize(palette=first, dither=Image.Dither.NONE) for frame in frames[1:]
    )
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    indexed[0].save(
        destination,
        format="GIF",
        save_all=True,
        append_images=indexed[1:],
        duration=round(1000 / fps),
        loop=0,
        optimize=False,
        disposal=2,
        comment=DISCLAIMER.encode("utf-8"),
    )
    return destination


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成 D-sub9 准静态规定姿态扫描 GIF。")
    parser.add_argument(
        "--output",
        type=Path,
        default=(
            PROJECT_ROOT
            / "deliverables/chinese_visual_package/animation/DSub9_准静态位姿扫描.gif"
        ),
    )
    parser.add_argument("--fps", type=int, default=10)
    args = parser.parse_args(argv)
    path = make_animation(args.output, fps=args.fps)
    print(f"已生成：{path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
