"""OpenCV inpaint engine."""

from __future__ import annotations

from PIL import Image

from translayer.engines.inpaint.base import BaseInpaintEngine
from translayer.ir.models import ImageTextRegion
from translayer.plugins import registry


@registry.register("inpaint", "opencv")
class OpenCVInpaintEngine(BaseInpaintEngine):
    """Erase text regions with OpenCV Telea inpainting for non-solid backgrounds."""

    name = "opencv"

    def erase(self, image_path: str, regions: list[ImageTextRegion], out_path: str) -> str:
        try:
            import cv2  # type: ignore[import-not-found]
            import numpy as np
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "OpenCV inpainting requires optional dependencies. "
                "Install them with: pip install 'translayer[inpaint-local]'"
            ) from exc

        with Image.open(image_path) as source:
            image = source.convert("RGB")

        textured_regions: list[ImageTextRegion] = []
        for region in regions:
            if region.background_kind == "solid":
                self._fill_solid(image, region)
            else:
                textured_regions.append(region)

        if textured_regions:
            mask = self.build_mask(image.size, textured_regions)
            rgb = np.array(image)
            bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            result = cv2.inpaint(bgr, np.array(mask), 3, cv2.INPAINT_TELEA)
            image = Image.fromarray(cv2.cvtColor(result, cv2.COLOR_BGR2RGB))

        image.save(out_path)
        return out_path
