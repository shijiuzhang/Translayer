"""Tesseract OCR adapter — local, no API key required.

Uses pytesseract + the system tesseract binary to detect text regions.
Words are grouped into line clusters by block/paragraph/line and split on
large horizontal gaps so that multi-column layouts do not collapse into
a single oversized region.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import median
from typing import Any

from PIL import Image

from translayer.engines.ocr.base import BaseOCREngine
from translayer.ir.models import ImageTextRegion
from translayer.plugins import registry


@registry.register("ocr", "tesseract")
class TesseractOCREngine(BaseOCREngine):
    name = "tesseract"

    # Minimum confidence (0-100) for a word to be considered.
    MIN_CONFIDENCE = 30

    # Gap multiplier: a horizontal gap larger than this times the median
    # word height on the line starts a new region.
    GAP_MULTIPLIER = 1.5

    # Absolute minimum gap in pixels.
    MIN_GAP_PX = 30

    def __init__(self, lang: str | None = None) -> None:
        self.lang = lang

    def detect(self, image_path: str) -> list[ImageTextRegion]:
        try:
            import pytesseract
        except ImportError as exc:
            raise RuntimeError(
                "Tesseract OCR support is optional. Install it with `pip install pytesseract`."
            ) from exc

        lang = self._tesseract_lang()
        with Image.open(image_path) as img:
            data = pytesseract.image_to_data(
                img,
                lang=lang,
                output_type=pytesseract.Output.DICT,
            )

        line_groups = self._group_words_by_line(data)
        regions: list[ImageTextRegion] = []
        for idxs in line_groups:
            clusters = self._split_line_into_clusters(data, idxs)
            for cluster in clusters:
                region = self._make_region_from_cluster(
                    data, cluster, idx=len(regions) + 1, image_path=image_path
                )
                if region is not None:
                    regions.append(region)
        return regions

    def _tesseract_lang(self) -> str | None:
        if self.lang:
            return self.lang
        return None

    def _group_words_by_line(self, data: dict[str, Any]) -> list[list[int]]:
        """Group word indices by (block, paragraph, line)."""
        raw: dict[tuple[int, int, int], list[int]] = defaultdict(list)
        for i in range(len(data["text"])):
            text = data["text"][i].strip()
            conf = float(data["conf"][i])
            if not text or conf < self.MIN_CONFIDENCE:
                continue
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            raw[key].append(i)

        groups = []
        for idxs in raw.values():
            idxs.sort(key=lambda i: data["left"][i])
            groups.append(idxs)
        return groups

    def _split_line_into_clusters(self, data: dict[str, Any], idxs: list[int]) -> list[list[int]]:
        """Split a line into separate regions on large horizontal gaps."""
        if not idxs:
            return []

        heights = [data["height"][i] for i in idxs]
        threshold = max(self.MIN_GAP_PX, self.GAP_MULTIPLIER * median(heights))

        clusters: list[list[int]] = []
        current = [idxs[0]]
        for i in idxs[1:]:
            prev = current[-1]
            prev_right = data["left"][prev] + data["width"][prev]
            gap = data["left"][i] - prev_right
            if gap > threshold:
                clusters.append(current)
                current = [i]
            else:
                current.append(i)
        clusters.append(current)
        return clusters

    def _make_region_from_cluster(
        self,
        data: dict[str, Any],
        idxs: list[int],
        idx: int,
        image_path: str,
    ) -> ImageTextRegion | None:
        texts = [data["text"][i] for i in idxs]
        full_text = " ".join(texts).strip()
        if not full_text:
            return None

        x = min(data["left"][i] for i in idxs)
        y = min(data["top"][i] for i in idxs)
        w = max(data["left"][i] + data["width"][i] for i in idxs) - x
        h = max(data["top"][i] + data["height"][i] for i in idxs) - y
        if w <= 0 or h <= 0:
            return None

        return self.make_region(idx, x, y, w, h, full_text, image_path=image_path)
