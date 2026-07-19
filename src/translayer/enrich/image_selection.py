"""Local image screening and routing with no paid provider calls.

The selector deliberately uses the local Tesseract executable. It separates
rich text-heavy graphics (whole-image localization) from simple labels that
are better served by the existing OCR/inpaint route, and excludes decorative
assets, logos, icons, and exact duplicates.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from typing import Protocol

from PIL import Image

from translayer.ir.models import (
    DocumentIR,
    ImageResource,
    ImageSelectionAnalysis,
    ImageTextRegion,
    Position,
)


@dataclass(frozen=True)
class ImageSelectionPolicy:
    min_width: int = 120
    min_height: int = 60
    min_pixel_area: int = 20_000
    min_word_confidence: float = 30.0
    review_confidence: float = 45.0
    min_text_chars: int = 6
    whole_image_text_chars: int = 30
    whole_image_words: int = 8
    whole_image_lines: int = 2
    whole_image_min_lexical_ratio: float = 0.30
    noisy_ocr_min_words: int = 10
    noisy_ocr_max_lexical_ratio: float = 0.26
    whole_image_min_display_ratio: float = 0.05
    small_asset_display_ratio: float = 0.025
    small_asset_max_text_chars: int = 24


@dataclass(frozen=True)
class ProbeWord:
    text: str
    confidence: float
    left: int
    top: int
    width: int
    height: int
    block: int
    paragraph: int
    line: int


@dataclass(frozen=True)
class ProbeResult:
    words: tuple[ProbeWord, ...]
    error: str | None = None


class TextProbe(Protocol):
    def probe(self, image_path: str) -> ProbeResult: ...


class TesseractTextProbe:
    """Fast local OCR probe using Tesseract TSV output directly."""

    def __init__(self, lang: str = "eng", timeout_seconds: int = 30) -> None:
        self.lang = lang
        self.timeout_seconds = timeout_seconds

    @property
    def cache_key(self) -> str:
        return f"tesseract:{self.lang}:psm11"

    def probe(self, image_path: str) -> ProbeResult:
        executable = shutil.which("tesseract")
        if not executable:
            return ProbeResult((), "tesseract executable not found")
        try:
            completed = subprocess.run(
                [
                    executable,
                    image_path,
                    "stdout",
                    "-l",
                    self.lang,
                    "--psm",
                    "11",
                    "tsv",
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return ProbeResult((), str(exc))
        if completed.returncode != 0:
            message = completed.stderr.strip() or f"tesseract exited {completed.returncode}"
            return ProbeResult((), message)

        words: list[ProbeWord] = []
        reader = csv.DictReader(io.StringIO(completed.stdout), delimiter="\t")
        for row in reader:
            text = (row.get("text") or "").strip()
            if not text:
                continue
            try:
                confidence = float(row.get("conf") or -1)
                words.append(
                    ProbeWord(
                        text=text,
                        confidence=confidence,
                        left=int(row.get("left") or 0),
                        top=int(row.get("top") or 0),
                        width=int(row.get("width") or 0),
                        height=int(row.get("height") or 0),
                        block=int(row.get("block_num") or 0),
                        paragraph=int(row.get("par_num") or 0),
                        line=int(row.get("line_num") or 0),
                    )
                )
            except (TypeError, ValueError):
                continue
        return ProbeResult(tuple(words))


class ImageSelector:
    """Classify every image using cheap geometry, hashing, and local OCR."""

    CACHE_VERSION = "image-selector-v2"

    def __init__(
        self,
        policy: ImageSelectionPolicy | None = None,
        probe: TextProbe | None = None,
        cache_dir: str | Path | None = None,
    ) -> None:
        self.policy = policy or ImageSelectionPolicy()
        self.probe = probe or TesseractTextProbe()
        self.cache_dir = Path(cache_dir) if cache_dir else None

    def analyze(self, ir: DocumentIR) -> list[ImageSelectionAnalysis]:
        seen: dict[str, str] = {}
        analyses: list[ImageSelectionAnalysis] = []
        for image in ir.resources.images:
            content_hash = _file_hash(image.data_ref)
            visual_hash = _visual_hash(image.data_ref)
            display_ratio = _display_area_ratio(ir, image)

            duplicate_of = seen.get(content_hash)
            if duplicate_of:
                analysis = ImageSelectionAnalysis(
                    route="reuse",
                    reason="exact_duplicate",
                    content_hash=content_hash,
                    visual_hash=visual_hash,
                    duplicate_of=duplicate_of,
                    display_area_ratio=display_ratio,
                )
            else:
                seen[content_hash] = image.id
                analysis = self._analyze_unique(
                    image, content_hash, visual_hash, display_ratio
                )
            image.selection = analysis
            analyses.append(analysis)
        return analyses

    def _analyze_unique(
        self,
        image: ImageResource,
        content_hash: str,
        visual_hash: str,
        display_ratio: float | None,
    ) -> ImageSelectionAnalysis:
        policy = self.policy
        if (
            image.width < policy.min_width
            or image.height < policy.min_height
            or image.width * image.height < policy.min_pixel_area
        ):
            return ImageSelectionAnalysis(
                route="skip",
                reason="too_small",
                content_hash=content_hash,
                visual_hash=visual_hash,
                display_area_ratio=display_ratio,
            )

        result = self._cached_probe(image.data_ref, content_hash)
        if result.error:
            return ImageSelectionAnalysis(
                route="review",
                reason="local_ocr_unavailable",
                content_hash=content_hash,
                visual_hash=visual_hash,
                display_area_ratio=display_ratio,
            )

        words = [
            word
            for word in result.words
            if word.confidence >= policy.min_word_confidence
            and word.text.strip()
            and _is_plausible_ocr_token(word.text)
        ]
        text = " ".join(word.text for word in words)
        alpha_chars = sum(character.isalpha() for character in text)
        text_chars = sum(character.isalnum() for character in text)
        meaningful_words = [word for word in words if _is_meaningful_word(word.text)]
        lexical_ratio = len(meaningful_words) / len(words) if words else 0.0
        line_keys = {(word.block, word.paragraph, word.line) for word in words}
        confidence = mean(word.confidence for word in words) if words else 0.0
        image_area = max(1, image.width * image.height)
        text_area = sum(max(0, word.width) * max(0, word.height) for word in words)
        text_area_ratio = min(1.0, text_area / image_area)

        metrics = dict(
            content_hash=content_hash,
            visual_hash=visual_hash,
            display_area_ratio=display_ratio,
            detected_text=text,
            text_chars=text_chars,
            alpha_chars=alpha_chars,
            word_count=len(words),
            meaningful_word_count=len(meaningful_words),
            lexical_word_ratio=round(lexical_ratio, 4),
            line_count=len(line_keys),
            mean_confidence=round(confidence, 2),
            text_area_ratio=round(text_area_ratio, 6),
        )
        if text_chars < policy.min_text_chars or alpha_chars < policy.min_text_chars:
            return ImageSelectionAnalysis(route="skip", reason="no_meaningful_text", **metrics)
        if confidence < policy.review_confidence:
            return ImageSelectionAnalysis(route="review", reason="low_ocr_confidence", **metrics)
        if (
            len(words) >= policy.noisy_ocr_min_words
            and lexical_ratio < policy.noisy_ocr_max_lexical_ratio
        ):
            return ImageSelectionAnalysis(route="review", reason="ocr_noise", **metrics)
        if (
            display_ratio is not None
            and display_ratio < policy.small_asset_display_ratio
            and text_chars <= policy.small_asset_max_text_chars
        ):
            return ImageSelectionAnalysis(route="skip", reason="likely_logo_or_icon", **metrics)
        if display_ratio is not None and display_ratio < policy.small_asset_display_ratio:
            return ImageSelectionAnalysis(
                route="review", reason="small_text_dense_asset", **metrics
            )
        if confidence < 60.0 and len(words) >= 3:
            return ImageSelectionAnalysis(
                route="review", reason="borderline_ocr_confidence", **metrics
            )
        if (
            display_ratio is not None
            and len(meaningful_words) <= 2
            and text_chars <= policy.small_asset_max_text_chars
        ):
            return ImageSelectionAnalysis(
                route="review", reason="ambiguous_short_text", **metrics
            )

        rich_text = (
            alpha_chars >= policy.whole_image_text_chars
            and len(meaningful_words) >= policy.whole_image_words
            and len(line_keys) >= policy.whole_image_lines
            and lexical_ratio >= policy.whole_image_min_lexical_ratio
        )
        large_enough = display_ratio is None or display_ratio >= policy.whole_image_min_display_ratio
        if rich_text and large_enough:
            return ImageSelectionAnalysis(
                route="whole_image", reason="text_rich_graphic", **metrics
            )
        return ImageSelectionAnalysis(route="region", reason="simple_text_regions", **metrics)

    def _cached_probe(self, image_path: str, content_hash: str) -> ProbeResult:
        if self.cache_dir is None:
            return self.probe.probe(image_path)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        policy_hash = hashlib.sha256(
            json.dumps(
                {
                    "policy": asdict(self.policy),
                    "probe": getattr(self.probe, "cache_key", type(self.probe).__name__),
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()[:12]
        cache_path = self.cache_dir / f"{self.CACHE_VERSION}-{policy_hash}-{content_hash}.json"
        if cache_path.exists():
            try:
                payload = json.loads(cache_path.read_text(encoding="utf-8"))
                return ProbeResult(
                    tuple(ProbeWord(**word) for word in payload.get("words", [])),
                    payload.get("error"),
                )
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                pass
        result = self.probe.probe(image_path)
        payload = {
            "words": [asdict(word) for word in result.words],
            "error": result.error,
        }
        cache_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return result


def regions_from_selection(image: ImageResource) -> list[ImageTextRegion]:
    """Make conservative line-level regions from the selector's OCR summary.

    The selector intentionally stores only aggregate evidence in the IR. This
    helper is reserved for future routing and currently returns existing OCR
    regions unchanged.
    """

    return image.text_regions


def plan_payload(
    ir: DocumentIR,
    targets: list[str],
    estimated_cost_per_image: float,
    budget_usd: float | None,
) -> dict:
    items = []
    route_counts: dict[str, int] = {}
    for image in ir.resources.images:
        selection = image.selection
        if selection is None:
            continue
        route_counts[selection.route] = route_counts.get(selection.route, 0) + 1
        items.append(
            {
                "image_id": image.id,
                "source_path": image.data_ref,
                "width": image.width,
                "height": image.height,
                **selection.model_dump(),
            }
        )
    paid_images = route_counts.get("whole_image", 0)
    projected_calls = paid_images * len(targets)
    estimated_cost = round(projected_calls * estimated_cost_per_image, 4)
    return {
        "provider_calls_made": 0,
        "targets": targets,
        "summary": {
            "total_images": len(ir.resources.images),
            "routes": route_counts,
            "projected_paid_calls": projected_calls,
            "estimated_cost_per_image_usd": estimated_cost_per_image,
            "estimated_total_cost_usd": estimated_cost,
            "budget_usd": budget_usd,
            "within_budget": budget_usd is None or estimated_cost <= budget_usd,
        },
        "images": items,
    }


def _file_hash(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _visual_hash(path: str) -> str:
    with Image.open(path) as image:
        normalized = image.convert("RGB").resize((64, 64), Image.Resampling.LANCZOS)
        return hashlib.sha256(normalized.tobytes()).hexdigest()


def _is_meaningful_word(text: str) -> bool:
    letters = "".join(character for character in text if character.isalpha())
    if any("\u3400" <= character <= "\u9fff" for character in letters):
        return len(letters) >= 2
    if len(letters) >= 3:
        return True
    return letters.upper() in {"AI", "BI", "IT", "IP", "KM", "RND", "SAP", "BOM", "CAD", "ERP", "LLM"}


def _is_plausible_ocr_token(text: str) -> bool:
    return len(text) <= 80 and "\\t" not in text and "\t" not in text and "\n" not in text


def _display_area_ratio(ir: DocumentIR, image: ImageResource) -> float | None:
    slide_width = ir.meta.engine_hints.get("slide_width")
    slide_height = ir.meta.engine_hints.get("slide_height")
    if not slide_width or not slide_height:
        return None
    block = next((block for block in ir.blocks if block.id == image.id), None)
    position: Position | None = block.layout.position if block and block.layout else None
    if position is None:
        return None
    return round((position.w * position.h) / (slide_width * slide_height), 6)
