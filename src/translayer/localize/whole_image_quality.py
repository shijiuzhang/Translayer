"""Deterministic text mapping and fail-closed QA for whole-image localization."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

from translayer.enrich.image_text import create_ocr_engine
from translayer.ir.models import (
    ImageLocalizationValidation,
    ImageResource,
    ImageTextRegion,
)
from translayer.languages import tesseract_language
from translayer.plugins import registry


class ImageLocalizationQualityError(RuntimeError):
    """Raised when a paid image result cannot safely enter the final document."""


def prepare_text_mappings(
    image: ImageResource,
    *,
    translation_engine: str,
    source_lang: str,
    target_lang: str,
) -> list[tuple[str, str]]:
    """Translate every OCR region first and return an explicit source/target map."""

    regions = [
        region
        for region in image.text_regions
        if region.translatable and region.source_text.strip()
    ]
    if not regions:
        image.localization_validation = ImageLocalizationValidation(
            status="failed",
            reason="pre_generation_ocr_empty",
        )
        raise ImageLocalizationQualityError(
            f"{image.id}: whole-image translation blocked because pre-generation OCR found no text"
        )

    translator = registry.get("translation", translation_engine)
    source_texts = [region.source_text.strip() for region in regions]
    translations = translator.translate(
        source_texts,
        src=source_lang,
        tgt=target_lang,
        context=(
            "These strings are OCR regions from one image. Translate every item, including "
            "headings and labels. Preserve true brands and acronyms only when appropriate."
        ),
    )
    if len(translations) != len(regions) or any(not str(value).strip() for value in translations):
        image.localization_validation = ImageLocalizationValidation(
            status="failed",
            expected_texts=source_texts,
            expected_translations=[str(value) for value in translations],
            reason="translation_mapping_incomplete",
        )
        raise ImageLocalizationQualityError(
            f"{image.id}: text translation did not return one non-empty value per OCR region"
        )

    mappings: list[tuple[str, str]] = []
    unchanged: list[str] = []
    for region, translated in zip(regions, translations, strict=True):
        target = str(translated).strip()
        region.target_text = target
        mappings.append((region.source_text.strip(), target))
        if (
            _normalized(region.source_text) == _normalized(target)
            and not _looks_like_protected_mark(region.source_text)
        ):
            unchanged.append(region.source_text.strip())

    image.localization_validation = ImageLocalizationValidation(
        status="not_run",
        expected_texts=[source for source, _target in mappings],
        expected_translations=[target for _source, target in mappings],
    )
    if unchanged:
        image.localization_validation.status = "failed"
        image.localization_validation.residual_source_texts = unchanged
        image.localization_validation.reason = "translation_mapping_unchanged"
        raise ImageLocalizationQualityError(
            f"{image.id}: translation mapping left source text unchanged: {', '.join(unchanged)}"
        )
    return mappings


def validate_localized_output(
    image: ImageResource,
    output_path: str,
    *,
    ocr_engine: str,
    source_lang: str,
    target_lang: str,
    detector: Any | None = None,
) -> ImageLocalizationValidation:
    """OCR the generated image and reject source leftovers or missing target text."""

    expected = list(
        zip(
            image.localization_validation.expected_texts,
            image.localization_validation.expected_translations,
            strict=False,
        )
    )
    if not expected:
        result = ImageLocalizationValidation(
            status="failed",
            reason="translation_mapping_missing",
        )
        image.localization_validation = result
        return result

    try:
        output_regions = (
            detector.detect(output_path)
            if detector is not None
            else _detect_multilingual_output(
                output_path,
                ocr_engine=ocr_engine,
                source_lang=source_lang,
                target_lang=target_lang,
            )
        )
    except Exception as exc:  # noqa: BLE001 - quality gate must fail closed
        result = ImageLocalizationValidation(
            status="failed",
            expected_texts=[source for source, _target in expected],
            expected_translations=[target for _source, target in expected],
            reason=f"post_generation_ocr_failed:{type(exc).__name__}",
        )
        image.localization_validation = result
        return result

    output_texts = [region.source_text.strip() for region in output_regions if region.source_text.strip()]
    if not output_texts:
        result = ImageLocalizationValidation(
            status="failed",
            expected_texts=[source for source, _target in expected],
            expected_translations=[target for _source, target in expected],
            reason="post_generation_ocr_empty",
        )
        image.localization_validation = result
        return result

    residuals: list[str] = []
    missing: list[str] = []
    for source, target in expected:
        if _looks_like_protected_mark(source) and _normalized(source) == _normalized(target):
            continue
        if (
            len(_normalized(source)) >= 4
            and _normalized(source) != _normalized(target)
            and _text_is_present(source, output_texts)
        ):
            residuals.append(source)
        if len(_normalized(target)) >= 4 and not _text_is_present(target, output_texts):
            missing.append(target)

    status = "failed" if residuals or missing else "passed"
    reason = None
    if residuals:
        reason = "residual_source_text"
    elif missing:
        reason = "missing_target_text"
    result = ImageLocalizationValidation(
        status=status,
        expected_texts=[source for source, _target in expected],
        expected_translations=[target for _source, target in expected],
        output_texts=output_texts,
        residual_source_texts=residuals,
        missing_target_texts=missing,
        reason=reason,
    )
    image.localization_validation = result
    return result


def _detect_multilingual_output(
    output_path: str,
    *,
    ocr_engine: str,
    source_lang: str,
    target_lang: str,
) -> list[ImageTextRegion]:
    registry.discover()
    if ocr_engine == "tesseract":
        languages = list(
            dict.fromkeys(
                [tesseract_language(source_lang), tesseract_language(target_lang)]
            )
        )
        detector = registry.get("ocr", "tesseract", lang="+".join(languages))
        return detector.detect(output_path)
    if ocr_engine == "paddle":
        regions: list[ImageTextRegion] = []
        seen: set[tuple[str, int, int]] = set()
        for language in (source_lang, target_lang):
            detector = create_ocr_engine("paddle", language)
            for region in detector.detect(output_path):
                key = (_normalized(region.source_text), region.bbox.x, region.bbox.y)
                if key not in seen:
                    seen.add(key)
                    regions.append(region)
        return regions
    return create_ocr_engine(ocr_engine, target_lang).detect(output_path)


def _text_is_present(expected: str, observed: list[str]) -> bool:
    needle = _normalized(expected)
    if len(needle) < 4:
        return True
    haystacks = [_normalized(value) for value in observed]
    combined = "".join(haystacks)
    if needle in combined:
        return True
    return any(
        len(value) >= 4 and SequenceMatcher(None, needle, value).ratio() >= 0.88
        for value in haystacks
    )


def _normalized(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _looks_like_protected_mark(text: str) -> bool:
    letters = "".join(character for character in text if character.isascii() and character.isalpha())
    tokens = re.findall(r"[A-Za-z0-9]+", text)
    return bool(letters) and letters.isupper() and len(tokens) <= 3 and len(letters) <= 16
