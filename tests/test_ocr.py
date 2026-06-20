from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from translayer.ir.models import ImageTextRegion
from translayer.plugins import registry


def _tiny_image(path: Path) -> tuple[int, int]:
    width, height = 200, 100
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    draw.text((12, 12), "Sample", fill="black")
    img.save(path)
    return width, height


def test_mock_ocr_returns_region(tmp_path) -> None:
    image_path = tmp_path / "ocr_sample.png"
    width, height = _tiny_image(image_path)
    registry.discover()
    engine = registry.get("ocr", "mock")

    regions = engine.detect(str(image_path))

    assert len(regions) >= 1
    region = regions[0]
    assert isinstance(region, ImageTextRegion)
    assert region.source_text
    assert 0 <= region.bbox.x < width
    assert 0 <= region.bbox.y < height
    assert region.bbox.w > 0
    assert region.bbox.h > 0
    assert region.bbox.x + region.bbox.w <= width
    assert region.bbox.y + region.bbox.h <= height
    assert region.background_kind in {"solid", "gradient", "photo"}


def test_ocr_registry_discovery() -> None:
    registry.discover()

    available = set(registry.available("ocr"))

    assert {"mock", "cloud_vision", "paddle"}.issubset(available)
