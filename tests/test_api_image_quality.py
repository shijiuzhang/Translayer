from __future__ import annotations

import importlib
import shutil

from PIL import Image

from translayer.api.jobs import ImageDecision, Job
from translayer.ir.models import (
    DocMeta,
    DocumentIR,
    ImageLocalizationValidation,
    ImageResource,
    ImageSelectionAnalysis,
    ImageTextRegion,
    Position,
    Resources,
)

api_app = importlib.import_module("translayer.api.app")


class _FakeGemini:
    def __init__(self, guard) -> None:
        self.guard = guard
        self.invalidated = False

    def localize(self, image_path, output, **_kwargs):
        self.guard.reserve()
        shutil.copyfile(image_path, output)
        return output

    def invalidate_cache(self, *_args, **_kwargs) -> None:
        self.invalidated = True


def _job(tmp_path) -> tuple[Job, ImageResource]:
    source = tmp_path / "source.png"
    Image.new("RGB", (320, 180), "white").save(source)
    selection = ImageSelectionAnalysis(
        route="whole_image",
        reason="text_rich_graphic",
        content_hash="content",
        visual_hash="visual",
    )
    image = ImageResource(
        id="s0-sh1-img",
        media_type="image/png",
        data_ref=str(source),
        width=320,
        height=180,
        selection=selection,
    )
    ir = DocumentIR(
        meta=DocMeta(source_lang="de", target_lang="en"),
        resources=Resources(images=[image]),
    )
    job = Job(
        id="quality-job",
        input_path=str(tmp_path / "input.pptx"),
        source_lang="de",
        target_lang="en",
        translation_engine="mock",
        ocr_engine="mock",
        inpaint_engine="pillow",
        ir=ir,
        work_dir=str(tmp_path),
        state="localizing_images",
        image_plan_locked=True,
        image_budget_usd=0.10,
        image_decisions={
            image.id: ImageDecision(
                suggested_action="whole_image",
                action="whole_image",
                source="user",
            )
        },
    )
    return job, image


def _install_fakes(monkeypatch, image, status: str):
    region = ImageTextRegion(
        id="r1",
        bbox=Position(x=10, y=10, w=100, h=20),
        source_text="Die Falle",
        target_text="The Trap",
    )

    def detect_image(_self, target, **_kwargs):
        target.text_regions = [region]
        return target.text_regions

    def prepare(target, **_kwargs):
        target.localization_validation = ImageLocalizationValidation(
            expected_texts=["Die Falle"],
            expected_translations=["The Trap"],
        )
        return [("Die Falle", "The Trap")]

    def validate(target, _output, **_kwargs):
        target.localization_validation = ImageLocalizationValidation(
            status=status,
            expected_texts=["Die Falle"],
            expected_translations=["The Trap"],
            output_texts=["Die Falle" if status == "failed" else "The Trap"],
            residual_source_texts=["Die Falle"] if status == "failed" else [],
            missing_target_texts=["The Trap"] if status == "failed" else [],
            reason="residual_source_text" if status == "failed" else None,
        )
        return target.localization_validation

    holder = {}
    api_app.registry.discover()
    original_get = api_app.registry.get

    def registry_get(kind, key, **kwargs):
        if (kind, key) != ("image_localization", "gemini"):
            return original_get(kind, key, **kwargs)
        holder["engine"] = _FakeGemini(kwargs["cost_guard"])
        return holder["engine"]

    monkeypatch.setattr(api_app.ImageTextEnricher, "detect_image", detect_image)
    monkeypatch.setattr(api_app, "prepare_text_mappings", prepare)
    monkeypatch.setattr(api_app, "validate_localized_output", validate)
    monkeypatch.setattr(api_app.registry, "get", registry_get)
    return holder


def test_failed_whole_image_quality_returns_to_human_review(monkeypatch, tmp_path) -> None:
    job, image = _job(tmp_path)
    holder = _install_fakes(monkeypatch, image, "failed")

    api_app._continue_after_image_review(job, allow_paid_api=True, max_budget_usd=0.10)

    assert job.state == "image_review", job.error
    assert job.image_decisions[image.id].action is None
    assert job.image_decisions[image.id].source == "quality_check"
    assert not job.image_plan_locked
    assert image.localized_data_ref is None
    assert image.rejected_data_ref
    assert image.localization_validation.residual_source_texts == ["Die Falle"]
    assert holder["engine"].invalidated
    assert job.paid_image_calls == 1


def test_passed_whole_image_quality_continues_to_text_review(monkeypatch, tmp_path) -> None:
    job, image = _job(tmp_path)
    holder = _install_fakes(monkeypatch, image, "passed")

    api_app._continue_after_image_review(job, allow_paid_api=True, max_budget_usd=0.10)

    assert job.state == "review", job.error
    assert job.image_decisions[image.id].action == "whole_image"
    assert image.localized_data_ref
    assert image.rejected_data_ref is None
    assert image.localization_validation.status == "passed"
    assert not holder["engine"].invalidated
    assert job.paid_image_calls == 1
    assert job.planned_paid_calls() == 0
