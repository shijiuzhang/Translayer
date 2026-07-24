from __future__ import annotations

import os

from PIL import Image

from translayer.fonts.layout import (
    fit_text,
    region_text_fits,
    render_text_canvas,
    render_text_in_box,
)
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


def test_fit_text_shrinks_before_breaking_an_english_word() -> None:
    registry = FontRegistry()
    font_path = registry.font_for_lang("en")

    size, lines = fit_text(
        "Collaboration",
        70,
        40,
        font_path,
        max_size=32,
    )

    assert size < 32
    assert lines == ["Collaboration"]


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


def test_region_fit_rejects_text_that_cannot_fit_at_minimum_size() -> None:
    region = ImageTextRegion(
        id="r1",
        bbox=Position(x=0, y=0, w=8, h=4),
        source_text="x",
        target_text="This translation cannot fit",
        font_estimate=Font(size=20),
    )

    assert not region_text_fits(region, lang="de")


def test_text_canvas_reflows_only_translated_text() -> None:
    regions = [
        ImageTextRegion(
            id="r1",
            bbox=Position(x=0, y=0, w=100, h=20),
            source_text="原始中文",
            target_text="Geprüfte Ausschreibungsunterlagen",
            font_estimate=Font(size=18),
        ),
        ImageTextRegion(
            id="r2",
            bbox=Position(x=0, y=30, w=100, h=20),
            source_text="更多中文",
            target_text="Ergebnis ist konform",
            font_estimate=Font(size=18),
        ),
    ]

    canvas = render_text_canvas((420, 180), regions, lang="de")

    assert canvas.size == (420, 180)
    assert canvas.getbbox() == (0, 0, 420, 180)
    assert canvas.getcolors(maxcolors=420 * 180) is not None
    assert len(canvas.getcolors(maxcolors=420 * 180) or []) > 1


def test_text_canvas_expands_instead_of_truncating_dense_content() -> None:
    region = ImageTextRegion(
        id="r1",
        bbox=Position(x=0, y=0, w=100, h=20),
        source_text="密集文本",
        target_text="Ausschreibungsunterlagen " * 80,
        font_estimate=Font(size=14),
    )

    canvas = render_text_canvas((140, 50), [region], lang="de")

    assert canvas.width == 140
    assert canvas.height > 50
