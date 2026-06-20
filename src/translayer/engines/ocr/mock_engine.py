from __future__ import annotations

from pathlib import Path

from PIL import Image

from translayer.engines.ocr.base import BaseOCREngine
from translayer.ir.models import ImageTextRegion
from translayer.plugins import registry


@registry.register("ocr", "mock")
class MockOCREngine(BaseOCREngine):
    name = "mock"

    def detect(self, image_path: str) -> list[ImageTextRegion]:
        with Image.open(image_path) as img:
            width, height = img.size
        text = Path(image_path).stem or "Sample"
        if text.lower() in {"image", "test", "sample"}:
            text = "Sample"
        x = max(0, width // 20)
        y = max(0, height // 20)
        w = max(1, width // 3)
        h = max(1, height // 4)
        return [self.make_region(1, x, y, w, h, text, image_path=image_path)]
