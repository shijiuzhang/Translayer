"""Tesseract OCR adapter — local, no API key required.

Uses pytesseract + the system tesseract binary to detect text regions.
Words are grouped into line clusters by block/paragraph/line and split on
large horizontal gaps so that multi-column layouts do not collapse into
a single oversized region.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from statistics import median
from typing import Any

from PIL import Image

from translayer.engines.ocr.base import BaseOCREngine
from translayer.ir.models import Font, ImageTextRegion, Position
from translayer.plugins import registry

_CJK = r"\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
_CJK_BETWEEN_RE = re.compile(rf"(?<=[{_CJK}])\s+(?=[{_CJK}])")
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,.;:!?，。！？；：、）》】」』])")
_SPACE_AFTER_OPEN_RE = re.compile(r"([（《【「『])\s+")


@dataclass(frozen=True)
class _LineCluster:
    indices: tuple[int, ...]
    block: int
    paragraph: int
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


@registry.register("ocr", "tesseract")
class TesseractOCREngine(BaseOCREngine):
    name = "tesseract"

    # Minimum confidence (0-100) for a word to be considered.
    MIN_CONFIDENCE = 40

    # Gap multiplier: a horizontal gap larger than this times the median
    # word height on the line starts a new region.
    GAP_MULTIPLIER = 1.5

    # Absolute minimum gap in pixels.
    MIN_GAP_PX = 30

    # Small screenshots often contain 8-14 px glyphs. Tesseract becomes much
    # more reliable when those images are enlarged before recognition.
    UPSCALE_BELOW_LONG_EDGE = 1200
    UPSCALE_FACTOR = 2.0

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
            source = img.convert("RGB")
            image_size = source.size
            scale = self._ocr_scale(source.size)
            if scale > 1:
                source = source.resize(
                    (
                        int(round(source.width * scale)),
                        int(round(source.height * scale)),
                    ),
                    Image.Resampling.LANCZOS,
                )
            data = pytesseract.image_to_data(
                source,
                lang=lang,
                config="--psm 3",
                output_type=pytesseract.Output.DICT,
            )

        line_groups = self._group_words_by_line(data)
        line_clusters = [
            self._line_cluster(data, cluster)
            for idxs in line_groups
            for cluster in self._split_line_into_clusters(data, idxs)
        ]
        paragraphs = self._merge_line_clusters(line_clusters)
        regions: list[ImageTextRegion] = []
        for paragraph in paragraphs:
            region = self._make_region_from_lines(
                data,
                paragraph,
                idx=len(regions) + 1,
                image_path=image_path,
                image_size=image_size,
                scale=scale,
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
            if (
                not text
                or conf < self.MIN_CONFIDENCE
                or not any(character.isalnum() for character in text)
            ):
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

    @staticmethod
    def _line_cluster(data: dict[str, Any], idxs: list[int]) -> _LineCluster:
        first = idxs[0]
        return _LineCluster(
            indices=tuple(idxs),
            block=int(data["block_num"][first]),
            paragraph=int(data["par_num"][first]),
            left=min(int(data["left"][i]) for i in idxs),
            top=min(int(data["top"][i]) for i in idxs),
            right=max(int(data["left"][i]) + int(data["width"][i]) for i in idxs),
            bottom=max(int(data["top"][i]) + int(data["height"][i]) for i in idxs),
        )

    def _merge_line_clusters(
        self, clusters: list[_LineCluster]
    ) -> list[list[_LineCluster]]:
        """Merge wrapped lines into paragraphs without collapsing columns."""
        grouped: dict[tuple[int, int], list[_LineCluster]] = defaultdict(list)
        for cluster in clusters:
            grouped[(cluster.block, cluster.paragraph)].append(cluster)

        paragraphs: list[list[_LineCluster]] = []
        for paragraph_clusters in grouped.values():
            chains: list[list[_LineCluster]] = []
            for cluster in sorted(
                paragraph_clusters, key=lambda item: (item.top, item.left)
            ):
                candidates: list[tuple[int, list[_LineCluster]]] = []
                for chain in chains:
                    previous = chain[-1]
                    if not self._clusters_are_wrapped_lines(previous, cluster):
                        continue
                    candidates.append((max(0, cluster.top - previous.bottom), chain))
                if candidates:
                    min(candidates, key=lambda item: item[0])[1].append(cluster)
                else:
                    chains.append([cluster])
            paragraphs.extend(chains)

        return sorted(
            paragraphs,
            key=lambda lines: (
                min(line.top for line in lines),
                min(line.left for line in lines),
            ),
        )

    @staticmethod
    def _clusters_are_wrapped_lines(previous: _LineCluster, current: _LineCluster) -> bool:
        if current.top < previous.top + max(1, previous.height // 2):
            return False
        vertical_gap = current.top - previous.bottom
        max_gap = max(12, int(1.8 * median([previous.height, current.height])))
        if vertical_gap > max_gap:
            return False

        overlap = max(
            0,
            min(previous.right, current.right) - max(previous.left, current.left),
        )
        overlap_ratio = overlap / max(1, min(previous.width, current.width))
        left_aligned = abs(previous.left - current.left) <= max(
            20, int(1.5 * median([previous.height, current.height]))
        )
        return overlap_ratio >= 0.2 or left_aligned

    def _make_region_from_lines(
        self,
        data: dict[str, Any],
        lines: list[_LineCluster],
        idx: int,
        image_path: str,
        image_size: tuple[int, int],
        scale: float,
    ) -> ImageTextRegion | None:
        line_texts = [
            _normalize_ocr_text(" ".join(str(data["text"][i]) for i in line.indices))
            for line in lines
        ]
        full_text = "\n".join(text for text in line_texts if text)
        if sum(character.isalnum() for character in full_text) < 2:
            return None

        erase_boxes = [
            self._scaled_padded_box(line, scale=scale, image_size=image_size)
            for line in lines
        ]
        x = min(box.x for box in erase_boxes)
        y = min(box.y for box in erase_boxes)
        right = max(box.x + box.w for box in erase_boxes)
        bottom = max(box.y + box.h for box in erase_boxes)
        w = right - x
        h = bottom - y
        if w <= 0 or h <= 0:
            return None

        font = self.estimate_font(image_path, Position(x=x, y=y, w=w, h=h))
        word_heights = [
            int(data["height"][i])
            for line in lines
            for i in line.indices
            if int(data["height"][i]) > 0
        ]
        if word_heights:
            font = Font(
                **font.model_dump(exclude={"size"}),
                size=max(5.0, round(median(word_heights) / scale * 0.9, 1)),
            )
        return self.make_region(
            idx,
            x,
            y,
            w,
            h,
            full_text,
            image_path=image_path,
            erase_boxes=erase_boxes,
            font_estimate=font,
        )

    @classmethod
    def _ocr_scale(cls, size: tuple[int, int]) -> float:
        return (
            cls.UPSCALE_FACTOR
            if max(size) < cls.UPSCALE_BELOW_LONG_EDGE
            else 1.0
        )

    @staticmethod
    def _scaled_padded_box(
        line: _LineCluster, *, scale: float, image_size: tuple[int, int]
    ) -> Position:
        width, height = image_size
        x = int(round(line.left / scale))
        y = int(round(line.top / scale))
        right = int(round(line.right / scale))
        bottom = int(round(line.bottom / scale))
        line_height = max(1, bottom - y)
        pad_x = max(2, int(round(line_height * 0.16)))
        pad_y = max(1, int(round(line_height * 0.12)))
        left = max(0, x - pad_x)
        top = max(0, y - pad_y)
        right = min(width, right + pad_x)
        bottom = min(height, bottom + pad_y)
        return Position(
            x=left,
            y=top,
            w=max(1, right - left),
            h=max(1, bottom - top),
        )


def _normalize_ocr_text(text: str) -> str:
    normalized = " ".join(text.split())
    normalized = _CJK_BETWEEN_RE.sub("", normalized)
    normalized = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", normalized)
    return _SPACE_AFTER_OPEN_RE.sub(r"\1", normalized)
