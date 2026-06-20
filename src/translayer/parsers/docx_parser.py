"""DOCX parser — extracts text, layout and images into DocumentIR.

Blocks are paragraph-level for translation quality. Each block carries a
SourceRef so the renderer can write translations back losslessly.
"""

from __future__ import annotations

import os
import tempfile

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from translayer.ir.models import (
    Block,
    DocMeta,
    DocumentIR,
    Font,
    ImageResource,
    Layout,
    Position,
    Run,
    SourceRef,
)
from translayer.plugins import registry


def _run_font(run) -> Font:
    f = run.font
    color = None
    if f.color and f.color.rgb:
        color = f"#{f.color.rgb}"
    return Font(
        name=f.name,
        size=float(f.size.pt) if f.size else None,
        color=color,
        bold=bool(f.bold) if f.bold is not None else False,
        italic=bool(f.italic) if f.italic is not None else False,
        underline=bool(f.underline) if f.underline is not None else False,
    )


def _heading_level(para: Paragraph) -> int | None:
    style = para.style
    if style and style.name and style.name.startswith("Heading"):
        try:
            return int(style.name.replace("Heading", "").strip())
        except (ValueError, TypeError):
            pass
    return None


def _list_style(para: Paragraph) -> bool:
    style_name = (para.style.name or "").lower()
    if "list" in style_name:
        return True
    pPr = para._element.find(qn("w:pPr"))
    if pPr is None:
        return False
    numPr = pPr.find(qn("w:numPr"))
    return numPr is not None


def _paragraph_position(para: Paragraph) -> Position | None:
    """Estimate position from paragraph index (approximate layout)."""
    return None


class DocxParser:
    name = "docx"

    def supported_formats(self) -> list[str]:
        return ["docx"]

    def parse(self, input_path: str, meta: dict) -> DocumentIR:
        asset_dir = meta.get("asset_dir") or tempfile.mkdtemp(prefix="translayer_docx_assets_")
        os.makedirs(asset_dir, exist_ok=True)

        doc = Document(input_path)
        ir = DocumentIR(
            meta=DocMeta(
                source_lang=meta.get("source_lang", "en"),
                target_lang=meta.get("target_lang", "zh"),
                doc_type="docx",
                title=meta.get("title"),
                glossary_ref=meta.get("glossary_ref"),
            )
        )

        block_counter = 0
        for element in doc.element.body:
            tag = element.tag.split("}")[-1] if "}" in element.tag else element.tag
            if tag == "p":
                para = Paragraph(element, doc)
                block_counter = self._parse_paragraph(para, block_counter, ir)
            elif tag == "tbl":
                table = Table(element, doc)
                block_counter = self._parse_table(table, block_counter, ir)

        self._extract_images(doc, ir, asset_dir)
        return ir

    def _parse_paragraph(self, para: Paragraph, counter: int, ir: DocumentIR) -> int:
        text = para.text.strip()
        if not text:
            return counter

        runs = [Run(text=r.text, font=_run_font(r)) for r in para.runs if r.text]
        heading_level = _heading_level(para)
        is_list = _list_style(para)

        if heading_level is not None:
            block_type: str = "heading"
            role = f"h{heading_level}"
        elif is_list:
            block_type = "list_item"
            role = "list_item"
        else:
            block_type = "paragraph"
            role = None

        block_id = f"docx-p{counter}"
        ir.blocks.append(
            Block(
                id=block_id,
                type=block_type,  # type: ignore[arg-type]
                semantic_role=role,
                runs=runs,
                source_text=text,
                layout=Layout(
                    page_index=0,
                    element_id=block_id,
                    base_font=_run_font(para.runs[0]) if para.runs else Font(),
                ),
                source_ref=SourceRef(
                    kind="heading" if heading_level else ("list_item" if is_list else "paragraph"),
                    slide_index=0,
                    shape_id=0,
                    paragraph_index=counter,
                ),
            )
        )
        return counter + 1

    def _parse_table(self, table: Table, counter: int, ir: DocumentIR) -> int:
        for r_idx, row in enumerate(table.rows):
            for c_idx, cell in enumerate(row.cells):
                for para in cell.paragraphs:
                    text = para.text.strip()
                    if not text:
                        continue
                    runs = [Run(text=r.text, font=_run_font(r)) for r in para.runs if r.text]
                    block_id = f"docx-t{counter}-r{r_idx}-c{c_idx}"
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

    def _extract_images(self, doc: Document, ir: DocumentIR, asset_dir: str) -> None:
        img_counter = 0
        for rel in doc.part.rels.values():
            if "image" in rel.reltype:
                try:
                    blob = rel.target_part.blob
                except AttributeError:
                    continue
                ext = rel.target_ref.rsplit(".", 1)[-1] if "." in rel.target_ref else "png"
                media_type = {
                    "png": "image/png",
                    "jpg": "image/jpeg",
                    "jpeg": "image/jpeg",
                    "gif": "image/gif",
                    "bmp": "image/bmp",
                    "emf": "image/emf",
                    "wmf": "image/wmf",
                }.get(ext.lower(), "image/png")

                img_id = f"docx-img{img_counter}"
                out_path = os.path.join(asset_dir, f"{img_id}.{ext}")
                with open(out_path, "wb") as fh:
                    fh.write(blob)

                ir.resources.images.append(
                    ImageResource(
                        id=img_id,
                        media_type=media_type,
                        data_ref=out_path,
                        width=0,
                        height=0,
                    )
                )
                ir.blocks.append(
                    Block(
                        id=img_id,
                        type="image",
                        translatable=False,
                        source_text="",
                        layout=Layout(page_index=0, element_id=img_id),
                        source_ref=SourceRef(
                            kind="image_region",
                            slide_index=0,
                            shape_id=0,
                            image_id=img_id,
                        ),
                    )
                )
                img_counter += 1


registry.register("parser", "docx")(DocxParser)
