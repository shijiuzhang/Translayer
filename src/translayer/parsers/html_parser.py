"""HTML parser — extracts translatable text, images and tables into DocumentIR.

Uses BeautifulSoup with lxml for robust HTML parsing. Translatable elements
are tagged with ``data-tl-id`` attributes so the renderer can write back
translations losslessly.
"""

from __future__ import annotations

import os
import tempfile

from bs4 import BeautifulSoup, NavigableString, Tag

from translayer.ir.models import (
    Block,
    DocMeta,
    DocumentIR,
    Font,
    Layout,
    Run,
    SourceRef,
)
from translayer.plugins import registry

_TRANSLATABLE_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "th", "td", "span", "a", "figcaption", "caption"}
_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_SKIP_TAGS = {"script", "style", "noscript", "code", "pre", "svg", "math"}


def _has_translatable_text(tag: Tag) -> bool:
    text = tag.get_text(strip=True)
    return bool(text) and len(text) > 0


def _direct_text(tag: Tag) -> str:
    """Get only the direct text of a tag, not nested translatable children."""
    parts = []
    for child in tag.children:
        if isinstance(child, NavigableString):
            parts.append(str(child))
        elif isinstance(child, Tag) and child.name not in _TRANSLATABLE_TAGS:
            parts.append(child.get_text())
    return "".join(parts).strip()


def _font_from_style(tag: Tag) -> Font:
    style = tag.get("style", "")
    font = Font()
    if "font-weight" in style and ("bold" in style or "700" in style or "800" in style or "900" in style):
        font.bold = True
    if "font-style" in style and "italic" in style:
        font.italic = True
    if "font-size" in style:
        import re
        m = re.search(r"font-size:\s*([\d.]+)", style)
        if m:
            try:
                font.size = float(m.group(1))
            except ValueError:
                pass
    if "color" in style:
        import re
        m = re.search(r"(?<!-)color:\s*(#[0-9a-fA-F]{3,6})", style)
        if m:
            font.color = m.group(1)
    return font


def _block_type(tag: Tag) -> str:
    name = tag.name.lower()
    if name in _HEADING_TAGS:
        return "heading"
    if name == "li":
        return "list_item"
    if name in ("td", "th"):
        return "table_cell"
    return "paragraph"


def _source_ref_kind(tag: Tag) -> str:
    name = tag.name.lower()
    if name in _HEADING_TAGS:
        return "heading"
    if name == "li":
        return "list_item"
    if name in ("td", "th"):
        return "table_cell"
    return "html_element"


class HtmlParser:
    name = "html"

    def supported_formats(self) -> list[str]:
        return ["html", "htm"]

    def parse(self, input_path: str, meta: dict) -> DocumentIR:
        asset_dir = meta.get("asset_dir") or tempfile.mkdtemp(prefix="translayer_html_assets_")
        os.makedirs(asset_dir, exist_ok=True)

        with open(input_path, encoding="utf-8") as fh:
            soup = BeautifulSoup(fh, "lxml")

        ir = DocumentIR(
            meta=DocMeta(
                source_lang=meta.get("source_lang", "en"),
                target_lang=meta.get("target_lang", "zh"),
                doc_type="html",
                title=self._extract_title(soup),
                glossary_ref=meta.get("glossary_ref"),
            )
        )

        counter = 0
        counter = self._walk(soup.body or soup, counter, ir, asset_dir)
        self._extract_images(soup, ir, asset_dir, counter)

        tagged_path = os.path.join(asset_dir, "tagged.html")
        with open(tagged_path, "w", encoding="utf-8") as fh:
            fh.write(str(soup))
        ir.meta.engine_hints["tagged_html"] = tagged_path

        return ir

    def _walk(self, parent: Tag, counter: int, ir: DocumentIR, asset_dir: str) -> int:
        for child in parent.children:
            if not isinstance(child, Tag):
                continue
            name = child.name.lower()
            if name in _SKIP_TAGS:
                continue

            if name in _TRANSLATABLE_TAGS and _has_translatable_text(child):
                counter = self._parse_text_element(child, counter, ir)
                continue

            if name == "table":
                counter = self._parse_table(child, counter, ir)
                continue

            if name == "img":
                counter = self._parse_img(child, counter, ir, asset_dir)
                continue

            if child.get_text(strip=True):
                counter = self._walk(child, counter, ir, asset_dir)

        return counter

    def _parse_text_element(self, tag: Tag, counter: int, ir: DocumentIR) -> int:
        text = tag.get_text(strip=True)
        if not text:
            return counter

        runs = [Run(text=text, font=_font_from_style(tag))]
        block_id = f"html-{counter}"
        tag["data-tl-id"] = block_id

        ir.blocks.append(
            Block(
                id=block_id,
                type=_block_type(tag),  # type: ignore[arg-type]
                semantic_role=tag.name.lower() if tag.name.lower() in _HEADING_TAGS else None,
                runs=runs,
                source_text=text,
                layout=Layout(page_index=0, element_id=block_id),
                source_ref=SourceRef(
                    kind=_source_ref_kind(tag),  # type: ignore[arg-type]
                    slide_index=0,
                    shape_id=0,
                    paragraph_index=counter,
                ),
            )
        )
        return counter + 1

    def _parse_table(self, table: Tag, counter: int, ir: DocumentIR) -> int:
        for r_idx, row in enumerate(table.find_all("tr")):
            cells = row.find_all(["td", "th"])
            for c_idx, cell in enumerate(cells):
                text = cell.get_text(strip=True)
                if not text:
                    continue
                runs = [Run(text=text, font=_font_from_style(cell))]
                block_id = f"html-t{counter}-r{r_idx}-c{c_idx}"
                cell["data-tl-id"] = block_id
                ir.blocks.append(
                    Block(
                        id=block_id,
                        type="table_cell",
                        runs=runs,
                        source_text=text,
                        layout=Layout(page_index=0, element_id=block_id),
                        source_ref=SourceRef(
                            kind="table_cell",
                            slide_index=0,
                            shape_id=0,
                            paragraph_index=counter,
                            row=r_idx,
                            col=c_idx,
                        ),
                    )
                )
                counter += 1
        return counter

    def _parse_img(self, img: Tag, counter: int, ir: DocumentIR, asset_dir: str) -> int:
        src = img.get("src", "")
        if not src:
            return counter

        img_id = f"html-img{counter}"

        alt = img.get("alt", "")
        if alt:
            alt = alt.strip()

        ir.blocks.append(
            Block(
                id=img_id,
                type="image",
                translatable=bool(alt),
                source_text=alt,
                layout=Layout(page_index=0, element_id=img_id),
                source_ref=SourceRef(
                    kind="html_image",
                    slide_index=0,
                    shape_id=0,
                    image_id=img_id,
                ),
            )
        )
        img["data-tl-id"] = img_id
        return counter + 1

    def _extract_images(self, soup: BeautifulSoup, ir: DocumentIR, asset_dir: str, counter: int) -> None:
        pass

    @staticmethod
    def _extract_title(soup: BeautifulSoup) -> str | None:
        title_tag = soup.find("title")
        if title_tag:
            return title_tag.get_text(strip=True)
        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True)
        return None


registry.register("parser", "html")(HtmlParser)
