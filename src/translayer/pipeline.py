"""Top-level pipeline: Parse -> Enrich -> Localize -> Render."""

from __future__ import annotations

import os

from translayer.enrich.glossary import GlossaryEnricher, load_glossary
from translayer.enrich.image_text import ImageTextEnricher
from translayer.enrich.roles import RoleEnricher
from translayer.ir.models import DocumentIR
from translayer.localize import layout_fit
from translayer.localize.orchestrator import localize
from translayer.plugins import registry


def _fmt_of(path: str) -> str:
    return os.path.splitext(path)[1].lstrip(".").lower()


def parse_document(input_path: str, source_lang: str, target_lang: str,
                   glossary: str | None = None, asset_dir: str | None = None) -> DocumentIR:
    registry.discover()
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


def enrich_document(ir: DocumentIR, images: bool = True,
                    ocr_engine: str | None = None) -> DocumentIR:
    from translayer.config import settings

    RoleEnricher().enrich(ir)
    GlossaryEnricher(load_glossary(ir.meta.glossary_ref)).enrich(ir)
    layout_fit.apply_constraints(ir)
    if images:
        ImageTextEnricher(ocr_engine or settings.ocr_engine).enrich(ir)
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
    asset_dir: str | None = None,
) -> DocumentIR:
    """End-to-end: parse -> enrich -> localize -> render."""
    ir = parse_document(input_path, source_lang, target_lang, glossary, asset_dir)
    enrich_document(ir, images=images, ocr_engine=ocr_engine)
    localize(ir, translation_engine=translation_engine,
             inpaint_engine=inpaint_engine, images=images)
    render_document(ir, input_path, output_path)
    return ir
