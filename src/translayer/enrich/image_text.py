"""In-image text detection enricher — runs an OCR engine over each image
resource and fills its ``text_regions``.
"""

from __future__ import annotations

from typing import Any

from translayer.ir.models import DocumentIR, ImageResource, ImageTextRegion
from translayer.languages import paddle_language, tesseract_language
from translayer.plugins import registry


class ImageTextEnricher:
    name = "image_text"

    def __init__(self, ocr_engine: str = "cloud_vision", source_lang: str | None = None):
        self.ocr_engine = ocr_engine
        self.source_lang = source_lang

    def enrich(self, ir: DocumentIR) -> DocumentIR:
        if not ir.resources.images:
            return ir
        engine = create_ocr_engine(self.ocr_engine, self.source_lang)
        for image in ir.resources.images:
            self.detect_image(image, engine=engine)
        return ir

    def detect_image(
        self,
        image: ImageResource,
        *,
        engine: Any | None = None,
        bypass_route: bool = False,
        strict: bool = False,
    ) -> list[ImageTextRegion]:
        """Populate OCR regions, optionally bypassing the initial routing gate.

        Whole-image localization calls this with ``bypass_route=True`` after the
        user approves paid processing. ``strict=True`` makes OCR failure block
        generation instead of silently treating the image as text-free.
        """

        if not bypass_route and image.selection and image.selection.route != "region":
            return image.text_regions
        if image.text_regions:
            return image.text_regions
        engine = engine or create_ocr_engine(self.ocr_engine, self.source_lang)
        try:
            image.text_regions = engine.detect(image.data_ref)
        except Exception:  # noqa: BLE001 - initial screening remains best-effort
            if strict:
                raise
            image.text_regions = []
        return image.text_regions


def create_ocr_engine(engine_name: str, language: str | None = None) -> Any:
    kwargs = {}
    if engine_name == "tesseract" and language:
        kwargs["lang"] = tesseract_language(language)
    elif engine_name == "paddle" and language:
        kwargs["lang"] = paddle_language(language)
    return registry.get("ocr", engine_name, **kwargs)
