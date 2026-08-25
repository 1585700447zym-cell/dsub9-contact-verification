from __future__ import annotations

from collections import Counter
import csv
import importlib
import json
from pathlib import Path

from PIL import Image, ImageFont
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS = PROJECT_ROOT / "reports" / "contact_validation_results.json"
EXPECTED_CHARTS = {
    "01_各工况峰值力.png",
    "02_各工况峰值力矩.png",
    "03_各工况最大穿透量.png",
}


def plots_module():
    return importlib.import_module("tools.visualization.plot_contact_results")


def fonts_module():
    return importlib.import_module("tools.visualization.font_support")


def test_chinese_font_is_a_real_file_that_renders_chinese():
    """Selecting a Latin-only font would ship square boxes in every chart."""

    font_path = fonts_module().find_chinese_font()
    font = ImageFont.truetype(str(font_path), 24)

    assert font_path.is_file()
    assert font.getbbox("中文图表")[2] > 0


def test_schema3_creates_twenty_rows_with_exact_profile_counts():
    """Dropping sensitivity rows or inflating their coverage changes the evidence."""

    rows = plots_module().load_result_rows(RESULTS)

    assert len(rows) == 20
    assert Counter(row.contact_profile for row in rows) == {
        "uncalibrated_diagnostic_v1": 16,
        "uncalibrated_low_response_v1": 2,
        "uncalibrated_high_response_v1": 2,
    }


def test_every_result_label_is_unique_and_marks_polygon32_as_approximate():
    """Duplicate labels would make the two combined-A scans indistinguishable."""

    rows = plots_module().load_result_rows(RESULTS)
    labels = [row.display_label for row in rows]

    assert len(labels) == len(set(labels)) == 20
    assert all("近似" in row.model_label for row in rows if row.collision_mode == "polygon32")


def test_unsupported_schema_is_rejected_instead_of_guessed(tmp_path: Path):
    """A future incompatible JSON layout must not produce misleading charts."""

    document = json.loads(RESULTS.read_text(encoding="utf-8"))
    document["schema_version"] = 4
    incompatible = tmp_path / "schema4.json"
    incompatible.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="schema-3"):
        plots_module().load_result_rows(incompatible)


def test_summary_csv_preserves_all_rows_and_required_chinese_columns(tmp_path: Path):
    """A summary export must not silently lose model/profile/termination context."""

    module = plots_module()
    rows = module.load_result_rows(RESULTS)
    output = tmp_path / "摘要.csv"
    module.write_summary_csv(rows, output)

    with output.open("r", encoding="utf-8-sig", newline="") as stream:
        records = list(csv.DictReader(stream))

    assert len(records) == 20
    assert set(records[0]) == {
        "工况",
        "模型类型",
        "接触配置",
        "终止原因",
        "峰值力_N_未标定",
        "峰值力矩_Nm_未标定",
        "最大穿透量_微米",
        "时间步_秒",
        "空间步长_米",
    }
    assert records[2]["峰值力_N_未标定"] == "0.001878360"


def test_generate_charts_writes_three_annotated_pngs_and_csv(tmp_path: Path):
    """Missing disclaimers or outputs would make the delivery package incomplete."""

    outputs = plots_module().generate_charts(RESULTS, tmp_path)

    assert {path.name for path in outputs if path.suffix == ".png"} == EXPECTED_CHARTS
    assert (tmp_path / "接触结果中文摘要.csv").is_file()
    for path in outputs:
        if path.suffix != ".png":
            continue
        with Image.open(path) as image:
            assert image.size[0] >= 1600
            assert image.size[1] >= 900
            assert "未经过实物标定" in image.info["Disclaimer"]

