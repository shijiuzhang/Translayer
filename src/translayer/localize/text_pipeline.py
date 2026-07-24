"""Text localization pipeline.

Groups translatable blocks by slide, builds whole-slide context and glossary,
calls the translation engine in batches honoring length constraints, and writes
``target_text`` back onto each block.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from translayer.enrich.grouping import group_by_slide, slide_context
from translayer.ir.models import Block, DocumentIR
from translayer.plugins import registry

_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_LATIN_RE = re.compile(r"[A-Za-z]")


def _normalized_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text or "").casefold()
    return "".join(char for char in normalized if char.isalnum())


def _looks_like_language(text: str, language: str) -> bool:
    if language == "zh":
        return bool(_CJK_RE.search(text or ""))
    if language in {"en", "de"}:
        return bool(_LATIN_RE.search(text or ""))
    return bool((text or "").strip())


def _text_groups(blocks: list[Block]) -> list[list[Block]]:
    grouped: dict[tuple, list[Block]] = defaultdict(list)
    for block in blocks:
        ref = block.source_ref
        grouped[(ref.kind, ref.shape_id, ref.row, ref.col)].append(block)
    return list(grouped.values())


def _parallel_layout(source: Block, target_group: list[Block]) -> bool:
    source_position = source.layout.position if source.layout else None
    target = target_group[0]
    target_position = target.layout.position if target.layout else None
    if source_position is None or target_position is None:
        return False

    sx1, sy1 = source_position.x, source_position.y
    sx2, sy2 = sx1 + source_position.w, sy1 + source_position.h
    tx1, ty1 = target_position.x, target_position.y
    tx2, ty2 = tx1 + target_position.w, ty1 + target_position.h
    vertical_overlap = max(0, min(sy2, ty2) - max(sy1, ty1))
    horizontal_overlap = max(0, min(sx2, tx2) - max(sx1, tx1))
    horizontal_gap = max(0, max(sx1, tx1) - min(sx2, tx2))
    vertical_gap = max(0, max(sy1, ty1) - min(sy2, ty2))

    same_row = (
        vertical_overlap >= min(source_position.h, target_position.h) * 0.5
        and horizontal_gap <= max(source_position.w, target_position.w) * 0.5
    )
    same_column = (
        horizontal_overlap >= min(source_position.w, target_position.w) * 0.5
        and vertical_gap <= max(source_position.h, target_position.h) * 0.5
    )
    return same_row or same_column


def _suppress_existing_target_duplicates(
    blocks: list[Block],
    *,
    source_lang: str,
    target_lang: str,
) -> None:
    """Blank a source-language block when its translation already sits beside it."""
    groups = _text_groups(blocks)
    candidates = []
    for group in groups:
        original = "".join(block.source_text for block in group)
        normalized = _normalized_text(original)
        if normalized and _looks_like_language(original, target_lang):
            candidates.append((group, normalized))

    for block in blocks:
        translated = block.target_text or ""
        normalized_translation = _normalized_text(translated)
        if (
            not normalized_translation
            or normalized_translation == _normalized_text(block.source_text)
            or not _looks_like_language(block.source_text, source_lang)
        ):
            continue
        for candidate_group, normalized_candidate in candidates:
            if block in candidate_group:
                continue
            if normalized_translation != normalized_candidate:
                continue
            if not _parallel_layout(block, candidate_group):
                continue
            block.target_text = ""
            for candidate in candidate_group:
                candidate.target_text = candidate.source_text
            break


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
        _suppress_existing_target_duplicates(
            blocks,
            source_lang=src,
            target_lang=tgt,
        )
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
