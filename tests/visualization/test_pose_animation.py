from __future__ import annotations

import importlib
from pathlib import Path

from PIL import Image, ImageChops, ImageStat
import pytest


DISCLAIMER = "准静态规定姿态扫描演示；不是自由动力学插入，不包含机器人或力控制器。"


def animation_module():
    return importlib.import_module("tools.visualization.make_pose_sweep_animation")


def test_default_pose_sequence_has_twelve_seconds_of_prescribed_stages():
    """A wrong sequence length or endpoint would misstate the demonstration."""

    poses = animation_module().build_pose_sequence(fps=10)

    assert len(poses) == 120
    assert poses[0].origin_z_m == pytest.approx(-0.005)
    assert poses[49].origin_z_m == pytest.approx(0.0)
    assert poses[69].x_offset_m == pytest.approx(0.0)
    assert poses[70].x_offset_m == pytest.approx(0.0001)
    assert poses[-1].x_offset_m == pytest.approx(0.00006)
    assert poses[-1].y_offset_m == pytest.approx(-0.00004)
    assert poses[-1].roll_rad == pytest.approx(0.02617993877991494)
    assert poses[-1].pitch_rad == pytest.approx(-0.02617993877991494)
    assert poses[-1].name == "组合偏差 A"


def test_generated_gif_is_readable_twelve_seconds_and_disclaimed(tmp_path: Path):
    """A static, truncated, or undisclaimed GIF must not enter the delivery package."""

    output = tmp_path / "pose-sweep.gif"
    animation_module().make_animation(output, fps=2, size=(480, 270))

    with Image.open(output) as image:
        assert image.format == "GIF"
        assert image.n_frames == 24
        assert image.info["loop"] == 0
        assert image.info["duration"] == 500
        assert DISCLAIMER.encode("utf-8") in image.info["comment"]
        frames = []
        for index in (0, image.n_frames // 2, image.n_frames - 1):
            image.seek(index)
            frame = image.convert("RGB")
            frames.append(frame.copy())
            disclaimer_band = frame.crop((0, 230, 480, 270))
            assert max(ImageStat.Stat(disclaimer_band).var) > 20.0

    assert ImageChops.difference(frames[0], frames[1]).getbbox() is not None
    assert ImageChops.difference(frames[1], frames[2]).getbbox() is not None
