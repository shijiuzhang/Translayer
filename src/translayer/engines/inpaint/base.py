"""Shared helpers for image inpainting engines."""

from __future__ import annotations

from abc import ABC, abstractmethod
from statistics import median

from PIL import Image, ImageDraw

from translayer.ir.models import ImageTextRegion


class BaseInpaintEngine(ABC):
    """Base class with common mask-building and solid-fill helpers."""

    name: str

    @abstractmethod
    def erase(self, image_path: str, regions: list[ImageTextRegion], out_path: str) -> str: ...

    @staticmethod
    def build_mask(size: tuple[int, int], regions: list[ImageTextRegion]) -> Image.Image:
        """Build a binary L-mode mask where text regions are white."""
        mask = Image.new("L", size, 0)
        draw = ImageDraw.Draw(mask)
        width, height = size
        for region in regions:
            if region.polygon:
                points = [
                    (max(0, min(width - 1, int(x))), max(0, min(height - 1, int(y))))
                    for x, y in region.polygon
                ]
                if points:
                    draw.polygon(points, fill=255)
                continue

            left, top, right, bottom = BaseInpaintEngine._bbox_bounds(region, size)
            if right > left and bottom > top:
                draw.rectangle((left, top, right - 1, bottom - 1), fill=255)
        return mask

    @staticmethod
    def _fill_solid(img: Image.Image, region: ImageTextRegion) -> None:
        """Fill a region bbox with the estimated surrounding background color."""
        left, top, right, bottom = BaseInpaintEngine._bbox_bounds(region, img.size)
        if right <= left or bottom <= top:
            return

        color = BaseInpaintEngine._surrounding_color(img, left, top, right, bottom)
        draw = ImageDraw.Draw(img)
        draw.rectangle((left, top, right - 1, bottom - 1), fill=color)

    @staticmethod
    def _bbox_bounds(region: ImageTextRegion, size: tuple[int, int]) -> tuple[int, int, int, int]:
        width, height = size
        box = region.bbox
        left = max(0, min(width, int(box.x)))
        top = max(0, min(height, int(box.y)))
        right = max(0, min(width, int(box.x + box.w)))
        bottom = max(0, min(height, int(box.y + box.h)))
        return left, top, right, bottom

    @staticmethod
    def _surrounding_color(
        img: Image.Image, left: int, top: int, right: int, bottom: int
    ) -> tuple[int, ...] | int:
        margin = max(2, min(12, max(right - left, bottom - top) // 3))
        ring_left = max(0, left - margin)
        ring_top = max(0, top - margin)
        ring_right = min(img.width, right + margin)
        ring_bottom = min(img.height, bottom + margin)

        pixels: list[tuple[int, ...] | int] = []
        for y in range(ring_top, ring_bottom):
            for x in range(ring_left, ring_right):
                if left <= x < right and top <= y < bottom:
                    continue
                pixels.append(img.getpixel((x, y)))

        if not pixels:
            crop = img.crop((left, top, right, bottom))
            pixels = list(crop.getdata())
        if not pixels:
            return 0

        return BaseInpaintEngine._median_color(pixels)

    @staticmethod
    def _median_color(pixels: list[tuple[int, ...] | int]) -> tuple[int, ...] | int:
        first = pixels[0]
        if isinstance(first, int):
            return int(median(int(pixel) for pixel in pixels))

        channel_count = len(first)
        return tuple(
            int(median(pixel[channel] for pixel in pixels if not isinstance(pixel, int)))
            for channel in range(channel_count)
        )
