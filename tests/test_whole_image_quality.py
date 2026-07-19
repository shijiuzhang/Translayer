from __future__ import annotations

from types import SimpleNamespace

import pytest

from translayer.ir.models import (
    ImageLocalizationValidation,
    ImageResource,
    ImageTextRegion,
    Position,
)
from translayer.localize import whole_image_quality as quality


def _region(region_id: str, text: str) -> ImageTextRegion:
    return ImageTextRegion(
        id=region_id,
        bbox=Position(x=10, y=10, w=100, h=20),
        source_text=text,
    )


def _image(*texts: str) -> ImageResource:
    return ImageResource(
        id="s1-image",
        media_type="image/png",
        data_ref="source.png",
        width=320,
        height=180,
        text_regions=[_region(f"r{index}", text) for index, text in enumerate(texts)],
    )


class _Detector:
    def __init__(self, *texts: str):
        self.texts = texts

    def detect(self, _path: str) -> list[ImageTextRegion]:
        return [_region(f"out{index}", text) for index, text in enumerate(self.texts)]


def test_prepare_text_mappings_translates_every_ocr_region(monkeypatch) -> None:
    image = _image("Die Falle", "Hohe Fehlerquote", "SAP")
    translator = SimpleNamespace(
        translate=lambda texts, **_kwargs: ["The Trap", "High Error Rate", "SAP"]
    )
    monkeypatch.setattr(quality.registry, "get", lambda *_args, **_kwargs: translator)

    mappings = quality.prepare_text_mappings(
        image,
        translation_engine="fake",
        source_lang="de",
        target_lang="en",
    )

    assert mappings == [
        ("Die Falle", "The Trap"),
        ("Hohe Fehlerquote", "High Error Rate"),
        ("SAP", "SAP"),
    ]
    assert [region.target_text for region in image.text_regions] == [
        "The Trap",
        "High Error Rate",
        "SAP",
    ]


def test_prepare_text_mappings_rejects_unchanged_natural_language(monkeypatch) -> None:
    image = _image("Die Falle")
    translator = SimpleNamespace(translate=lambda texts, **_kwargs: texts)
    monkeypatch.setattr(quality.registry, "get", lambda *_args, **_kwargs: translator)

    with pytest.raises(quality.ImageLocalizationQualityError, match="Die Falle"):
        quality.prepare_text_mappings(
            image,
            translation_engine="fake",
            source_lang="de",
            target_lang="en",
        )

    assert image.localization_validation.status == "failed"
    assert image.localization_validation.reason == "translation_mapping_unchanged"


def test_validation_rejects_residual_source_and_missing_target() -> None:
    image = _image("Die Falle", "Hohe Fehlerquote")
    image.localization_validation = ImageLocalizationValidation(
        expected_texts=["Die Falle", "Hohe Fehlerquote"],
        expected_translations=["The Trap", "High Error Rate"],
    )

    result = quality.validate_localized_output(
        image,
        "output.png",
        ocr_engine="fake",
        source_lang="de",
        target_lang="en",
        detector=_Detector("Die Falle", "High Error Rate"),
    )

    assert result.status == "failed"
    assert result.reason == "residual_source_text"
    assert result.residual_source_texts == ["Die Falle"]
    assert result.missing_target_texts == ["The Trap"]


def test_validation_passes_only_when_every_target_is_present() -> None:
    image = _image("Die Falle", "Hohe Fehlerquote")
    image.localization_validation = ImageLocalizationValidation(
        expected_texts=["Die Falle", "Hohe Fehlerquote"],
        expected_translations=["The Trap", "High Error Rate"],
    )

    result = quality.validate_localized_output(
        image,
        "output.png",
        ocr_engine="fake",
        source_lang="de",
        target_lang="en",
        detector=_Detector("The Trap", "High Error Rate"),
    )

    assert result.status == "passed"
    assert not result.residual_source_texts
    assert not result.missing_target_texts


def test_validation_fails_closed_when_output_ocr_fails() -> None:
    image = _image("Die Falle")
    image.localization_validation = ImageLocalizationValidation(
        expected_texts=["Die Falle"],
        expected_translations=["The Trap"],
    )
    detector = SimpleNamespace(
        detect=lambda _path: (_ for _ in ()).throw(RuntimeError("OCR unavailable"))
    )

    result = quality.validate_localized_output(
        image,
        "output.png",
        ocr_engine="fake",
        source_lang="de",
        target_lang="en",
        detector=detector,
    )

    assert result.status == "failed"
    assert result.reason == "post_generation_ocr_failed:RuntimeError"
