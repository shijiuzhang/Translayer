"""Layout fitting — translate length constraints into the IR and apply simple
font-shrink heuristics so translated text does not overflow its box.

PPTX positions are in EMU (914400 per inch ≈ 12700 per point). We estimate how
many characters fit in a text box from its width/height and base font size.
"""

from __future__ import annotations

from translayer.ir.models import Block, DocumentIR

EMU_PER_PT = 12700.0
# Average glyph advance as a fraction of font size (Latin ~0.5, CJK ~1.0).
_AVG_GLYPH_W = 0.55
_LINE_HEIGHT = 1.2


def _font_size_pt(block: Block) -> float:
    if block.runs and block.runs[0].font.size:
        return block.runs[0].font.size
    if block.layout and block.layout.base_font.size:
        return block.layout.base_font.size
    return 18.0


def estimate_max_chars(block: Block) -> int | None:
    if not block.layout or not block.layout.position:
        return None
    pos = block.layout.position
    size_pt = _font_size_pt(block)
    if size_pt <= 0:
        return None
    box_w_pt = pos.w / EMU_PER_PT
    box_h_pt = pos.h / EMU_PER_PT
    chars_per_line = max(1, int(box_w_pt / (size_pt * _AVG_GLYPH_W)))
    lines = max(1, int(box_h_pt / (size_pt * _LINE_HEIGHT)))
    return chars_per_line * lines


def apply_constraints(ir: DocumentIR) -> DocumentIR:
    """Populate Constraints.max_chars for every translatable block."""
    for block in ir.translatable_blocks():
        max_chars = estimate_max_chars(block)
        if max_chars:
            block.constraints.max_chars = max_chars
    return ir
