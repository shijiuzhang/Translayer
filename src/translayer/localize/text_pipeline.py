"""Text localization pipeline.

Groups translatable blocks by slide, builds whole-slide context and glossary,
calls the translation engine in batches honoring length constraints, and writes
``target_text`` back onto each block.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from translayer.enrich.grouping import group_by_slide, slide_context
from translayer.ir.models import DocumentIR
from translayer.plugins import registry


def localize_text(
    ir: DocumentIR,
    engine_name: str = "openai",
    engine_options: dict | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> DocumentIR:
    groups = group_by_slide(ir)
    if not groups:
        return ir

    engine = registry.get("translation", engine_name, **(engine_options or {}))
    src, tgt = ir.meta.source_lang, ir.meta.target_lang
    total_slides = len(groups)
    total_blocks = sum(len(blocks) for blocks in groups.values())
    completed_blocks = 0

    for index, (slide, blocks) in enumerate(groups.items()):
        if progress_callback:
            progress_callback(
                {
                    "completed": index,
                    "total": total_slides,
                    "completed_items": completed_blocks,
                    "total_items": total_blocks,
                    "current": slide + 1,
                    "stage": "translating",
                }
            )
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
        completed_blocks += len(blocks)
        if progress_callback:
            progress_callback(
                {
                    "completed": index + 1,
                    "total": total_slides,
                    "completed_items": completed_blocks,
                    "total_items": total_blocks,
                    "current": slide + 1,
                    "stage": "completed" if index + 1 == total_slides else "translating",
                }
            )

    return ir
