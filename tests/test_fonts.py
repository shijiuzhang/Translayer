from __future__ import annotations

import os

from PIL import Image

from translayer.fonts.layout import fit_text, render_text_in_box
from translayer.fonts.registry import FontRegistry
from translayer.ir.models import Font, ImageTextRegion, Position


def test_font_for_lang_returns_existing_paths() -> None:
    registry = FontRegistry()

    assert os.path.exists(registry.font_for_lang("zh"))
    assert os.path.exists(registry.font_for_lang("en"))


def test_fit_text_shrinks_and_wraps_chinese_text() -> None:
    registry = FontRegistry()
    font_path = registry.font_for_lang("zh")
    text = "季度营收报告显示亚太地区增长强劲并超过全年目标"

    small_size, small_lines = fit_text(text, 90, 42, font_path, max_size=36)
    large_size, _ = fit_text(text, 280, 100, font_path, max_size=36)

    assert small_size < large_size
    assert len(small_lines) > 1


def test_render_text_in_box_draws_only_inside_bbox() -> None:
    image = Image.new("RGB", (300, 120), "white")
    bbox = Position(x=20, y=15, w=260, h=90)
    region = ImageTextRegion(
        id="r1",
        bbox=bbox,
        source_text="Quarterly revenue report",
        target_text="季度营收报告",
        font_estimate=Font(size=42, color="#111111"),
        align="center",
    )

    render_text_in_box(image, region, lang="zh")
    pixels = image.load()

    inside_changed = any(
        pixels[x, y] != (255, 255, 255)
        for y in range(bbox.y, bbox.y + bbox.h)
        for x in range(bbox.x, bbox.x + bbox.w)
    )
    outside_changed = any(
        pixels[x, y] != (255, 255, 255)
        for y in range(image.height)
        for x in range(image.width)
        if not (bbox.x <= x < bbox.x + bbox.w and bbox.y <= y < bbox.y + bbox.h)
    )

    assert inside_changed
    assert not outside_changed
