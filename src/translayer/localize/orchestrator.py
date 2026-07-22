"""Localize orchestrator — runs the text and image sub-pipelines."""

from __future__ import annotations

from translayer.config import settings
from translayer.ir.models import DocumentIR
from translayer.localize.image_pipeline import localize_images
from translayer.localize.text_pipeline import localize_text


def localize(
    ir: DocumentIR,
    translation_engine: str | None = None,
    inpaint_engine: str | None = None,
    images: bool = True,
    translation_options: dict | None = None,
) -> DocumentIR:
    t_engine = translation_engine or settings.translation_engine
    i_engine = inpaint_engine or settings.inpaint_engine

    localize_text(ir, engine_name=t_engine, engine_options=translation_options)
    if images:
        localize_images(
            ir,
            translation_engine=t_engine,
            inpaint_engine=i_engine,
            translation_options=translation_options,
        )
    return ir
