"""Glossary / terminology matching.

Loads a simple term map (CSV ``source,target`` or dict) and records TermHits on
blocks so the translation engine is forced to honor preferred terms.
"""

from __future__ import annotations

import csv
import os

from translayer.ir.models import DocumentIR, TermHit


def load_glossary(ref: str | None) -> dict[str, str]:
    if not ref or not os.path.exists(ref):
        return {}
    terms: dict[str, str] = {}
    with open(ref, encoding="utf-8") as fh:
        reader = csv.reader(fh)
        for row in reader:
            if len(row) >= 2 and row[0].strip():
                terms[row[0].strip()] = row[1].strip()
    return terms


class GlossaryEnricher:
    name = "glossary"

    def __init__(self, glossary: dict[str, str] | None = None):
        self.glossary = glossary or {}

    def enrich(self, ir: DocumentIR) -> DocumentIR:
        if not self.glossary and ir.meta.glossary_ref:
            self.glossary = load_glossary(ir.meta.glossary_ref)
        if not self.glossary:
            return ir
        lowered = {k.lower(): (k, v) for k, v in self.glossary.items()}
        for block in ir.blocks:
            if not block.source_text:
                continue
            hay = block.source_text.lower()
            for term_l, (term, preferred) in lowered.items():
                start = hay.find(term_l)
                if start >= 0:
                    block.term_hits.append(
                        TermHit(term=term, preferred=preferred, start=start, end=start + len(term))
                    )
        return ir
