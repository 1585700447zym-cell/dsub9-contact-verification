from __future__ import annotations

import importlib
from pathlib import Path

import numpy as np
from PIL import Image, ImageStat

from tools.visualization.runtime import input_hashes, load_model


EXPECTED_SCREENSHOTS = {
    "01_对齐场景总览.png",
    "02_碰撞几何叠加.png",
    "03_九针九孔局部放大.png",
    "04_正X偏移100微米.png",
    "05_组合偏差工况A.png",
    "06_正式SDF与回退模型对照.png",
}


def renderer_module():
    return importlib.import_module("tools.visualization.render_scenes")


def test_display_styling_changes_only_rgba_not_collision_physics():
    """A display helper must not accidentally change reviewed contact behavior."""

    module = renderer_module()
    model = load_model("polygon32")
    protected = {
        "contype": model.geom_contype.copy(),
        "conaffinity": model.geom_conaffinity.copy(),
        "friction": model.geom_friction.copy(),
        "solref": model.geom_solref.copy(),
        "solimp": model.geom_solimp.copy(),
        "margin": model.geom_margin.copy(),
    }
    original_rgba = model.geom_rgba.copy()

    module.style_model_for_display(model, "collision_overlay")

    assert not np.array_equal(model.geom_rgba, original_rgba)
    for name, values in protected.items():
        assert np.array_equal(getattr(model, f"geom_{name}"), values), name


def test_generate_screenshots_writes_required_annotated_images_without_input_changes(
    tmp_path: Path,
):
    """Missing, tiny, blank, or destructive renders must fail the delivery contract."""

    before = input_hashes()
    outputs = renderer_module().generate_screenshots(tmp_path)
    after = input_hashes()

    assert {path.name for path in outputs} == EXPECTED_SCREENSHOTS
    assert before == after
    for path in outputs:
        assert path.stat().st_size > 20_000
        with Image.open(path) as image:
            assert image.format == "PNG"
            assert image.size == (1600, 900)
            assert image.info["Title"]
            assert image.info["Caption"]
            assert image.info["GenerationMethod"] == "MuJoCo offscreen + Pillow annotation"
            assert max(ImageStat.Stat(image.convert("RGB")).var) > 100.0


def test_comparison_image_explicitly_marks_polygon32_as_approximation(tmp_path: Path):
    """The side-by-side image must not imply the fallback is an analytic hole."""

    path = renderer_module().generate_screenshots(tmp_path)[-1]

    with Image.open(path) as image:
        assert image.info["ModelMode"] == "sdf+polygon32"
        assert "近似" in image.info["Caption"]


def test_overview_records_and_displays_the_positive_z_insertion_direction(
    tmp_path: Path,
):
    """An overview without a visible direction cue would not explain insertion."""

    overview = renderer_module().generate_screenshots(tmp_path)[0]

    with Image.open(overview) as image:
        assert image.info["InsertionDirection"] == "+world/task Z"
