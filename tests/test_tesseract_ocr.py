"""Tesseract OCR adapter tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw, ImageFont

from translayer.engines.ocr.tesseract_engine import TesseractOCREngine

pytestmark = pytest.mark.skipif(
    not TesseractOCREngine.__module__,
    reason="tesseract engine not importable",
)


def _make_text_image(tmp_path: Path, text: str) -> str:
    """Create a simple white image with black text."""
    img = Image.new("RGB", (400, 100), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 24)
    except OSError:
        font = ImageFont.load_default()
    draw.text((20, 30), text, fill="black", font=font)
    path = str(tmp_path / "text.png")
    img.save(path)
    return path


def test_tesseract_detects_text(tmp_path: Path) -> None:
    engine = TesseractOCREngine()
    path = _make_text_image(tmp_path, "Hello World")
    regions = engine.detect(path)
    texts = [r.source_text for r in regions]
    assert any("Hello" in t or "World" in t for t in texts)


def test_tesseract_splits_columns(tmp_path: Path) -> None:
    """Two headings on the same horizontal line should not merge."""
    img = Image.new("RGB", (600, 120), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 28)
    except OSError:
        font = ImageFont.load_default()
    draw.text((30, 40), "Left Side", fill="black", font=font)
    draw.text((380, 40), "Right Side", fill="black", font=font)
    path = str(tmp_path / "columns.png")
    img.save(path)

    engine = TesseractOCREngine()
    regions = engine.detect(path)
    texts = [r.source_text for r in regions]
    assert any("Left" in t for t in texts)
    assert any("Right" in t for t in texts)
    # They should be separate regions, not one merged box.
    assert len(regions) >= 2


def test_tesseract_upscales_small_images_and_merges_wrapped_lines(
    tmp_path: Path, monkeypatch
) -> None:
    path = tmp_path / "small.png"
    Image.new("RGB", (500, 300), "white").save(path)
    seen_size = None

    data = {
        "text": ["第一行", "内容", "第二行", "继续"],
        "conf": ["95", "94", "96", "93"],
        "block_num": [1, 1, 1, 1],
        "par_num": [1, 1, 1, 1],
        "line_num": [1, 1, 2, 2],
        "left": [40, 150, 40, 150],
        "top": [40, 40, 80, 80],
        "width": [90, 70, 90, 70],
        "height": [24, 24, 24, 24],
    }

    def fake_image_to_data(image, **_kwargs):
        nonlocal seen_size
        seen_size = image.size
        return data

    fake_module = SimpleNamespace(
        image_to_data=fake_image_to_data,
        Output=SimpleNamespace(DICT="dict"),
    )
    monkeypatch.setitem(__import__("sys").modules, "pytesseract", fake_module)

    regions = TesseractOCREngine(lang="chi_sim+eng").detect(str(path))

    assert seen_size == (1000, 600)
    assert len(regions) == 1
    assert regions[0].source_text == "第一行内容\n第二行继续"
    assert len(regions[0].erase_boxes) == 2
    assert regions[0].bbox.x < 20
    assert regions[0].bbox.y < 20
    assert regions[0].bbox.w < 120
    assert regions[0].bbox.h < 50
