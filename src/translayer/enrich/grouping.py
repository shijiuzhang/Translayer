"""Context grouping — groups blocks by slide so the translation engine can use
whole-slide context for higher quality, coherent translations.
"""

from __future__ import annotations

from translayer.ir.models import Block, DocumentIR


def group_by_slide(ir: DocumentIR) -> dict[int, list[Block]]:
    groups: dict[int, list[Block]] = {}
    for block in ir.translatable_blocks():
        slide = block.layout.slide_index if block.layout else 0
        groups.setdefault(slide, []).append(block)
    return groups


def slide_context(blocks: list[Block], limit: int = 1200) -> str:
    """A compact context string from a slide's text."""
    joined = " / ".join(b.source_text for b in blocks if b.source_text)
    return joined[:limit]
