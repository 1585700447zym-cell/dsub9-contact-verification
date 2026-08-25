from __future__ import annotations

import csv
from pathlib import Path
import re

from PIL import Image
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE = PROJECT_ROOT / "deliverables" / "chinese_visual_package"
GUIDE = PACKAGE / "中文使用说明.md"
REQUIRED_SECTIONS = (
    "本交付包解决什么问题",
    "三分钟快速开始",
    "项目目录和每类文件的用途",
    "公头、母头、9 针、9 孔和 D 形外部导向如何建模",
    "视觉几何和碰撞几何的区别",
    "正式 SDF 模型和 polygon32 回退模型的区别",
    "坐标系、插入轴、5+4 针阵列和单位",
    "双击启动正式 SDF 场景",
    "双击启动免插件场景",
    "MuJoCo viewer 常用操作",
    "六张截图逐图说明",
    "三张图表如何阅读",
    "20 条验证结果分别代表什么",
    "为什么结果不能视为真实插入力",
    "常见故障排查",
    "重新生成回退模型、截图、图表和动画",
    "哪些核心文件不应随意修改",
    "下一阶段研究如何接入",
    "当前模型已完成和未完成的边界",
    "复现与引用建议",
)
REQUIRED_FILES = (
    "启动正式SDF场景.cmd",
    "启动免插件场景.cmd",
    "screenshots/01_对齐场景总览.png",
    "screenshots/02_碰撞几何叠加.png",
    "screenshots/03_九针九孔局部放大.png",
    "screenshots/04_正X偏移100微米.png",
    "screenshots/05_组合偏差工况A.png",
    "screenshots/06_正式SDF与回退模型对照.png",
    "charts/01_各工况峰值力.png",
    "charts/02_各工况峰值力矩.png",
    "charts/03_各工况最大穿透量.png",
    "charts/接触结果中文摘要.csv",
    "animation/DSub9_准静态位姿扫描.gif",
)


def test_guide_has_all_twenty_required_sections_and_scientific_disclaimers():
    """A code-oriented or scientifically ambiguous guide is not acceptable."""

    text = GUIDE.read_text(encoding="utf-8")

    for index, title in enumerate(REQUIRED_SECTIONS, start=1):
        assert f"## {index}. {title}" in text
    assert "未经过实物标定" in text
    assert "不能作为实物插入力预测或安全阈值" in text
    assert "不是自由动力学插入" in text
    assert "polygon32 是近似" in text


@pytest.mark.parametrize("relative", REQUIRED_FILES)
def test_every_required_delivery_file_exists_and_is_nonempty(relative: str):
    """A guide link is useless when its concrete artifact is missing."""

    path = PACKAGE / relative

    assert path.is_file(), relative
    assert path.stat().st_size > 0, relative


def test_every_local_markdown_image_link_resolves():
    """Moving the package must not leave broken screenshot/chart links."""

    text = GUIDE.read_text(encoding="utf-8")
    links = re.findall(r"!\[[^]]*\]\(([^)]+)\)", text)

    assert len(links) >= 10
    assert all((PACKAGE / link).is_file() for link in links)


def test_final_csv_has_twenty_rows_and_final_media_are_readable():
    """The checked-in outputs must be real media and complete data, not placeholders."""

    with (PACKAGE / "charts/接触结果中文摘要.csv").open(
        "r", encoding="utf-8-sig", newline=""
    ) as stream:
        assert len(list(csv.DictReader(stream))) == 20

    for relative in REQUIRED_FILES:
        if not relative.endswith((".png", ".gif")):
            continue
        with Image.open(PACKAGE / relative) as image:
            image.verify()

