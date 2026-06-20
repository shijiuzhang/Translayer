"""LaMa inpaint engine."""

from __future__ import annotations

from PIL import Image

from translayer.engines.inpaint.base import BaseInpaintEngine
from translayer.ir.models import ImageTextRegion
from translayer.plugins import registry


@registry.register("inpaint", "lama")
class LamaInpaintEngine(BaseInpaintEngine):
    """Erase text regions with simple-lama-inpainting when installed."""

    name = "lama"

    def erase(self, image_path: str, regions: list[ImageTextRegion], out_path: str) -> str:
        try:
            from simple_lama_inpainting import SimpleLama  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "LaMa inpainting requires simple-lama-inpainting. "
                "Install it with: pip install simple-lama-inpainting"
            ) from exc

        with Image.open(image_path) as source:
            image = source.convert("RGB")
        mask = self.build_mask(image.size, regions)
        result = SimpleLama()(image, mask)
        result.save(out_path)
        return out_path
