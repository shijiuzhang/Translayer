"""HTML renderer — writes translations back into the original HTML file.

Locates elements by the ``data-tl-id`` attribute set during parsing, and
replaces their text content with the translated text. Preserves all HTML
structure, attributes and non-translatable content.
"""

from __future__ import annotations

import os

from bs4 import NavigableString, Tag

from translayer.ir.models import Block, DocumentIR
from translayer.plugins import registry

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover
    BeautifulSoup = None  # type: ignore[assignment,misc]


class HtmlRenderer:
    name = "html"

    def supported_formats(self) -> list[str]:
        return ["html", "htm"]

    def render(self, ir: DocumentIR, input_path: str, output_path: str) -> None:
        tagged_path = ir.meta.engine_hints.get("tagged_html")
        read_path = tagged_path if tagged_path and os.path.exists(tagged_path) else input_path

        with open(read_path, encoding="utf-8") as fh:
            soup = BeautifulSoup(fh, "lxml")

        for block in ir.blocks:
            if block.target_text is None:
                continue
            if block.type == "image":
                self._render_image_alt(block, soup)
                continue
            self._render_text_block(block, soup)

        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write(str(soup))

    def _render_text_block(self, block: Block, soup: Tag) -> None:
        ref = block.source_ref
        tl_id = f"html-{ref.paragraph_index}"

        if ref.kind == "table_cell":
            tl_id = self._find_table_cell_id(soup, ref)

        element = soup.find(attrs={"data-tl-id": tl_id})
        if element is None:
            return

        self._set_element_text(element, block.target_text or "")

    def _render_image_alt(self, block: Block, soup: Tag) -> None:
        ref = block.source_ref
        if ref.image_id is None:
            return
        element = soup.find(attrs={"data-tl-id": ref.image_id})
        if element is None or not isinstance(element, Tag):
            return
        if block.target_text:
            element["alt"] = block.target_text

    def _find_table_cell_id(self, soup: Tag, ref) -> str:
        """Search for matching table cell by data-tl-id pattern."""
        for tag in soup.find_all(attrs={"data-tl-id": True}):
            tl_id = tag.get("data-tl-id", "")
            if tl_id.startswith("html-t") and f"r{ref.row}-c{ref.col}" in tl_id:
                return tl_id
        return ""

    @staticmethod
    def _set_element_text(element: Tag, text: str) -> None:
        """Replace element text while preserving nested non-text tags."""
        preserve_tags = set()
        for child in element.find_all(True):
            if child.name in ("img", "br", "hr", "input", "strong", "em", "b", "i", "u"):
                preserve_tags.add(child)

        for child in list(element.children):
            if isinstance(child, NavigableString):
                child.extract()
            elif child not in preserve_tags:
                child.extract()

        if preserve_tags:
            element.insert(0, NavigableString(text))
        else:
            element.string = text


registry.register("renderer", "html")(HtmlRenderer)
