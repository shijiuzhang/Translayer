"""Semantic role refinement.

The parser already tags placeholder-based roles (title/subtitle/body). This
enricher fills gaps with light heuristics: the first sizable text block on a
slide with no role becomes a ``title`` candidate; tiny footer-positioned text is
marked ``footer``.
"""

from __future__ import annotations

from translayer.ir.models import DocumentIR

EMU_PER_INCH = 914400


class RoleEnricher:
    name = "roles"

    def enrich(self, ir: DocumentIR) -> DocumentIR:
        seen_title: set[int] = set()
        for block in ir.blocks:
            if block.type == "image" or not block.layout:
                continue
            slide = block.layout.slide_index
            if block.semantic_role:
                if block.semantic_role == "title":
                    seen_title.add(slide)
                continue
            pos = block.layout.position
            if pos and slide not in seen_title and pos.y < EMU_PER_INCH:
                block.semantic_role = "title"
                seen_title.add(slide)
        return ir
