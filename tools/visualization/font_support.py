"""Deterministic Chinese font selection for charts and image annotations."""

from __future__ import annotations

import functools
from pathlib import Path

from matplotlib import font_manager


PREFERRED_FONTS = (
    "Noto Sans SC",
    "Microsoft YaHei",
    "SimHei",
    "SimSun",
)


@functools.lru_cache(maxsize=1)
def find_chinese_font() -> Path:
    """Return the first available reviewed Chinese-capable system font."""

    by_name = {
        item.name: Path(item.fname)
        for item in font_manager.fontManager.ttflist
        if Path(item.fname).is_file()
    }
    for name in PREFERRED_FONTS:
        if name in by_name:
            return by_name[name]
    checked = "、".join(PREFERRED_FONTS)
    raise RuntimeError(f"未找到可用中文字体；已检查：{checked}。")

