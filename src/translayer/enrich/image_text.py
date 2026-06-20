"""In-image text detection enricher — runs an OCR engine over each image
resource and fills its ``text_regions``.
"""

from __future__ import annotations

from translayer.ir.models import DocumentIR
from translayer.plugins import registry


class ImageTextEnricher:
    name = "image_text"

    def __init__(self, ocr_engine: str = "cloud_vision"):
        self.ocr_engine = ocr_engine

    def enrich(self, ir: DocumentIR) -> DocumentIR:
        if not ir.resources.images:
            return ir
        engine = registry.get("ocr", self.ocr_engine)
        for image in ir.resources.images:
            if image.text_regions:
                continue
            try:
                regions = engine.detect(image.data_ref)
            except Exception:  # noqa: BLE001 - OCR failures must not break the run
                regions = []
            image.text_regions = regions
        return ir
