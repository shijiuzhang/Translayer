from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from translayer.engines.ocr.base import BaseOCREngine
from translayer.ir.models import ImageTextRegion
from translayer.plugins import registry


@registry.register("ocr", "paddle")
class PaddleOCREngine(BaseOCREngine):
    name = "paddle"

    def detect(self, image_path: str) -> list[ImageTextRegion]:
        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise RuntimeError(
                "Paddle OCR support is optional. Install it with `pip install 'translayer[ocr-local]'`."
            ) from exc

        ocr = PaddleOCR(use_angle_cls=True, lang="en")
        raw = ocr.ocr(image_path, cls=True)
        regions: list[ImageTextRegion] = []
        for item in _iter_paddle_lines(raw):
            parsed = _parse_line(item)
            if parsed is None:
                continue
            polygon, text = parsed
            xs = [point[0] for point in polygon]
            ys = [point[1] for point in polygon]
            x = min(xs)
            y = min(ys)
            w = max(xs) - x
            h = max(ys) - y
            if w <= 0 or h <= 0 or not text.strip():
                continue
            regions.append(
                self.make_region(
                    len(regions) + 1,
                    x,
                    y,
                    w,
                    h,
                    text.strip(),
                    image_path=image_path,
                    polygon=[(int(round(px)), int(round(py))) for px, py in polygon],
                )
            )
        return regions


def _iter_paddle_lines(raw: Any) -> Iterable[Any]:
    if isinstance(raw, dict):
        for key in ("res", "results", "rec_texts"):
            value = raw.get(key)
            if value is not None:
                yield from _iter_paddle_lines(value)
        return
    if not isinstance(raw, list):
        return
    if _parse_line(raw) is not None:
        yield raw
        return
    for item in raw:
        yield from _iter_paddle_lines(item)


def _parse_line(item: Any) -> tuple[list[tuple[float, float]], str] | None:
    if not isinstance(item, (list, tuple)) or len(item) < 2:
        return None
    polygon_raw = item[0]
    text_raw = item[1]
    if not isinstance(polygon_raw, (list, tuple)) or len(polygon_raw) < 4:
        return None
    polygon: list[tuple[float, float]] = []
    for point in polygon_raw:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            return None
        try:
            polygon.append((float(point[0]), float(point[1])))
        except (TypeError, ValueError):
            return None
    if isinstance(text_raw, (list, tuple)) and text_raw:
        text_raw = text_raw[0]
    if not isinstance(text_raw, str):
        return None
    return polygon, text_raw
