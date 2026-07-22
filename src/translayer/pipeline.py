"""Top-level pipeline: Parse -> Enrich -> Localize -> Render."""

from __future__ import annotations

import os

from translayer.enrich.glossary import GlossaryEnricher, load_glossary
from translayer.enrich.image_selection import ImageSelector, TesseractTextProbe
from translayer.enrich.image_text import ImageTextEnricher
from translayer.enrich.roles import RoleEnricher
from translayer.ir.models import DocumentIR
from translayer.languages import normalize_language, tesseract_language
from translayer.localize import layout_fit
from translayer.localize.orchestrator import localize
from translayer.plugins import registry


def _fmt_of(path: str) -> str:
    return os.path.splitext(path)[1].lstrip(".").lower()


def parse_document(input_path: str, source_lang: str, target_lang: str,
                   glossary: str | None = None, asset_dir: str | None = None) -> DocumentIR:
    registry.discover()
    source_lang = normalize_language(source_lang)
    target_lang = normalize_language(target_lang)
    if source_lang == target_lang:
        raise ValueError("source and target languages must be different")
    parser = registry.find_parser(_fmt_of(input_path))
    return parser.parse(
        input_path,
        {
            "source_lang": source_lang,
            "target_lang": target_lang,
            "glossary_ref": glossary,
            "asset_dir": asset_dir,
        },
    )


def enrich_document(
    ir: DocumentIR,
    images: bool = True,
    ocr_engine: str | None = None,
    screen_images: bool | None = None,
) -> DocumentIR:
    from translayer.config import settings

    RoleEnricher().enrich(ir)
    GlossaryEnricher(load_glossary(ir.meta.glossary_ref)).enrich(ir)
    layout_fit.apply_constraints(ir)
    if images:
        should_screen = settings.image_selection_enabled if screen_images is None else screen_images
        if should_screen:
            ImageSelector(
                probe=TesseractTextProbe(lang=tesseract_language(ir.meta.source_lang)),
                cache_dir=settings.image_selection_cache_dir,
            ).analyze(ir)
        ImageTextEnricher(
            ocr_engine or settings.ocr_engine,
            source_lang=ir.meta.source_lang,
        ).enrich(ir)
    return ir


def render_document(ir: DocumentIR, input_path: str, output_path: str) -> None:
    registry.discover()
    renderer = registry.find_renderer(_fmt_of(output_path))
    renderer.render(ir, input_path, output_path)


def translate_document(
    input_path: str,
    output_path: str,
    source_lang: str = "en",
    target_lang: str = "zh",
    *,
    translation_engine: str | None = None,
    ocr_engine: str | None = None,
    inpaint_engine: str | None = None,
    glossary: str | None = None,
    images: bool = True,
    screen_images: bool | None = None,
    asset_dir: str | None = None,
    translation_options: dict | None = None,
) -> DocumentIR:
    """End-to-end: parse -> enrich -> localize -> render."""
    ir = parse_document(input_path, source_lang, target_lang, glossary, asset_dir)
    enrich_document(
        ir,
        images=images,
        ocr_engine=ocr_engine,
        screen_images=screen_images,
    )
    localize(
        ir,
        translation_engine=translation_engine,
        inpaint_engine=inpaint_engine,
        images=images,
        translation_options=translation_options,
    )
    render_document(ir, input_path, output_path)
    return ir
