"""Tesseract OCR adapter tests."""

from __future__ import annotations

from pathlib import Path

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
