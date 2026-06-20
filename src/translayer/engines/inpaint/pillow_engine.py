"""Pure Pillow inpaint engine."""

from __future__ import annotations

from PIL import Image

from translayer.engines.inpaint.base import BaseInpaintEngine
from translayer.ir.models import ImageTextRegion
from translayer.plugins import registry


@registry.register("inpaint", "pillow")
class PillowInpaintEngine(BaseInpaintEngine):
    """Erase text regions with solid surrounding-color fills.

    This default engine is pure Pillow and always available. It uses the same
    best-effort solid fill for gradient/photo regions; OpenCV or LaMa engines
    handle those backgrounds better when their optional dependencies are installed.
    """

    name = "pillow"

    def erase(self, image_path: str, regions: list[ImageTextRegion], out_path: str) -> str:
        with Image.open(image_path) as source:
            image = source.convert("RGB")
        for region in regions:
            self._fill_solid(image, region)
        image.save(out_path)
        return out_path
