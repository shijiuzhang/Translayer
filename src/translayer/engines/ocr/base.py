from __future__ import annotations

from abc import ABC, abstractmethod
from collections import Counter
from collections.abc import Iterable
from math import sqrt
from pathlib import Path
from typing import Any, Literal

from PIL import Image

from translayer.ir.models import Font, ImageTextRegion, Position

BackgroundKind = Literal["solid", "gradient", "photo"]
Align = Literal["left", "center", "right"]
RGB = tuple[int, int, int]


class BaseOCREngine(ABC):
    """Base class for OCR adapters with shared image-derived estimates."""

    name: str

    @abstractmethod
    def detect(self, image_path: str) -> list[ImageTextRegion]:
        """Detect text regions in an image."""

    def make_region(
        self,
        idx: int,
        x: int,
        y: int,
        w: int,
        h: int,
        text: str,
        **kw: Any,
    ) -> ImageTextRegion:
        image_path = kw.pop("image_path", None)
        bbox = Position(x=int(round(x)), y=int(round(y)), w=int(round(w)), h=int(round(h)))
        polygon = kw.pop("polygon", None)
        erase_boxes = kw.pop("erase_boxes", [])
        align: Align = kw.pop("align", "left")
        target_text = kw.pop("target_text", None)
        translatable = kw.pop("translatable", True)
        font_estimate = kw.pop("font_estimate", None)
        background_kind = kw.pop("background_kind", None)

        if image_path:
            bbox = self._clamp_bbox(image_path, bbox)
            if font_estimate is None:
                font_estimate = self.estimate_font(image_path, bbox)
            if background_kind is None:
                background_kind = self.estimate_background_kind(image_path, bbox)

        if font_estimate is None:
            font_estimate = Font()
        elif isinstance(font_estimate, dict):
            font_estimate = Font(**font_estimate)

        if background_kind is None:
            background_kind = "solid"

        return ImageTextRegion(
            id=f"reg{idx}",
            bbox=bbox,
            polygon=polygon,
            erase_boxes=erase_boxes,
            source_text=text,
            target_text=target_text,
            font_estimate=font_estimate,
            align=align,
            background_kind=background_kind,
            translatable=translatable,
        )

    def estimate_background_kind(self, image_path: str, bbox: Position) -> BackgroundKind:
        with Image.open(image_path) as img:
            rgb = img.convert("RGB")
            samples = list(self._background_samples(rgb, bbox))
        if len(samples) < 2:
            return "solid"

        means = [sum(pixel[i] for pixel in samples) / len(samples) for i in range(3)]
        variance = sum(
            sum((pixel[i] - means[i]) ** 2 for i in range(3)) / 3 for pixel in samples
        ) / len(samples)
        stddev = sqrt(variance)
        unique_ratio = len({_quantize(pixel, 24) for pixel in samples}) / len(samples)

        if stddev < 10 and unique_ratio < 0.08:
            return "solid"
        if stddev < 35 and unique_ratio < 0.35:
            return "gradient"
        return "photo"

    def estimate_font(self, image_path: str, bbox: Position) -> Font:
        color = self.estimate_text_color(image_path, bbox)
        size = max(1.0, round(bbox.h * 0.8, 1)) if bbox.h else None
        return Font(color=color, size=size)

    def estimate_text_color(self, image_path: str, bbox: Position) -> str | None:
        with Image.open(image_path) as img:
            rgb = img.convert("RGB")
            bbox = self._clamp_bbox_for_image(rgb.size, bbox)
            crop = rgb.crop((bbox.x, bbox.y, bbox.x + bbox.w, bbox.y + bbox.h))
            if not crop.size[0] or not crop.size[1]:
                return None
            pixels = list(_sample_image(crop))
            background = self._dominant_color(self._background_samples(rgb, bbox))

        if not pixels:
            return None
        if background is None:
            background = self._dominant_color(pixels)
        if background is None:
            return None

        buckets = Counter(_quantize(pixel, 16) for pixel in pixels)
        min_count = max(1, len(pixels) // 200)
        candidates = [item for item in buckets.items() if item[1] >= min_count]
        if not candidates:
            candidates = list(buckets.items())
        text_color, _ = max(candidates, key=lambda item: _distance(item[0], background))
        return _hex(text_color)

    def _clamp_bbox(self, image_path: str, bbox: Position) -> Position:
        with Image.open(image_path) as img:
            return self._clamp_bbox_for_image(img.size, bbox)

    @staticmethod
    def _clamp_bbox_for_image(size: tuple[int, int], bbox: Position) -> Position:
        width, height = size
        x = max(0, min(bbox.x, max(0, width - 1)))
        y = max(0, min(bbox.y, max(0, height - 1)))
        w = max(1, min(bbox.w, width - x))
        h = max(1, min(bbox.h, height - y))
        return Position(x=x, y=y, w=w, h=h)

    @staticmethod
    def _background_samples(img: Image.Image, bbox: Position) -> Iterable[RGB]:
        width, height = img.size
        pad = max(3, min(width, height, max(bbox.w, bbox.h)) // 20)
        left = max(0, bbox.x - pad)
        top = max(0, bbox.y - pad)
        right = min(width, bbox.x + bbox.w + pad)
        bottom = min(height, bbox.y + bbox.h + pad)
        if left >= right or top >= bottom:
            return []

        step = max(1, min(right - left, bottom - top) // 30)
        samples: list[RGB] = []
        for yy in range(top, bottom, step):
            for xx in range(left, right, step):
                inside = bbox.x <= xx < bbox.x + bbox.w and bbox.y <= yy < bbox.y + bbox.h
                near_edge = yy < bbox.y or yy >= bbox.y + bbox.h or xx < bbox.x or xx >= bbox.x + bbox.w
                if not inside or near_edge:
                    samples.append(img.getpixel((xx, yy)))
        return samples

    @staticmethod
    def _dominant_color(pixels: Iterable[RGB]) -> RGB | None:
        buckets = Counter(_quantize(pixel, 16) for pixel in pixels)
        if not buckets:
            return None
        return buckets.most_common(1)[0][0]


def _sample_image(img: Image.Image) -> Iterable[RGB]:
    width, height = img.size
    step = max(1, int(sqrt((width * height) / 2500)))
    for y in range(0, height, step):
        for x in range(0, width, step):
            yield img.getpixel((x, y))


def _quantize(pixel: RGB, bucket: int) -> RGB:
    return tuple(max(0, min(255, round(channel / bucket) * bucket)) for channel in pixel)  # type: ignore[return-value]


def _distance(a: RGB, b: RGB) -> float:
    return sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def _hex(pixel: RGB) -> str:
    return f"#{pixel[0]:02X}{pixel[1]:02X}{pixel[2]:02X}"


def image_mime_type(image_path: str) -> str:
    suffix = Path(image_path).suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".webp":
        return "image/webp"
    return "image/png"
