from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from translayer.engines.ocr.tesseract_engine import TesseractOCREngine
from translayer.enrich.image_text import ImageTextEnricher
from translayer.ir.models import DocMeta, DocumentIR, ImageResource, ImageTextRegion, Resources
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


@pytest.mark.parametrize(
    ("engine_name", "source", "expected"),
    [
        ("tesseract", "en", "eng"),
        ("tesseract", "de", "deu+eng"),
        ("tesseract", "zh", "chi_sim+eng"),
        ("paddle", "en", "en"),
        ("paddle", "de", "german"),
        ("paddle", "zh", "ch"),
    ],
)
def test_image_enricher_selects_source_language(
    engine_name: str, source: str, expected: str, monkeypatch
) -> None:
    captured = {}

    class _Engine:
        def detect(self, _path):
            return []

    def fake_get(kind, key, **kwargs):
        captured.update(kind=kind, key=key, kwargs=kwargs)
        return _Engine()

    monkeypatch.setattr("translayer.enrich.image_text.registry.get", fake_get)
    ir = DocumentIR(
        meta=DocMeta(source_lang=source, target_lang="en" if source != "en" else "de"),
        resources=Resources(
            images=[
                ImageResource(
                    id="image",
                    media_type="image/png",
                    data_ref="unused.png",
                    width=100,
                    height=100,
                )
            ]
        ),
    )

    ImageTextEnricher(engine_name, source_lang=source).enrich(ir)

    assert captured == {"kind": "ocr", "key": engine_name, "kwargs": {"lang": expected}}


def test_tesseract_accepts_decimal_confidence_values() -> None:
    data = {
        "text": ["Umsatz"],
        "conf": ["96.531"],
        "block_num": [1],
        "par_num": [1],
        "line_num": [1],
        "left": [10],
        "height": [20],
    }

    assert TesseractOCREngine(lang="deu+eng")._group_words_by_line(data) == [[0]]


def test_tesseract_ignores_symbol_only_and_low_confidence_tokens() -> None:
    data = {
        "text": ["+", "可信文字", "噪声"],
        "conf": ["99", "88", "20"],
        "block_num": [1, 1, 1],
        "par_num": [1, 1, 1],
        "line_num": [1, 1, 1],
        "left": [0, 20, 80],
        "height": [10, 10, 10],
    }

    assert TesseractOCREngine(lang="chi_sim+eng")._group_words_by_line(data) == [[1]]
