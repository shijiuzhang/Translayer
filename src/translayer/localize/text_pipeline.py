"""Text localization pipeline.

Groups translatable blocks by slide, builds whole-slide context and glossary,
calls the translation engine in batches honoring length constraints, and writes
``target_text`` back onto each block.
"""

from __future__ import annotations

from translayer.enrich.grouping import group_by_slide, slide_context
from translayer.ir.models import DocumentIR
from translayer.plugins import registry


def localize_text(ir: DocumentIR, engine_name: str = "openai") -> DocumentIR:
    groups = group_by_slide(ir)
    if not groups:
        return ir

    engine = registry.get("translation", engine_name)
    src, tgt = ir.meta.source_lang, ir.meta.target_lang

    for _slide, blocks in groups.items():
        texts = [b.source_text for b in blocks]
        context = slide_context(blocks)
        glossary: dict[str, str] = {}
        for b in blocks:
            for hit in b.term_hits:
                glossary[hit.term] = hit.preferred
        max_chars = [b.constraints.max_chars for b in blocks]

        results = engine.translate(
            texts, src=src, tgt=tgt,
            context=context,
            glossary=glossary or None,
            max_chars=max_chars,
        )
        for block, translated in zip(blocks, results, strict=False):
            block.target_text = translated

    return ir
