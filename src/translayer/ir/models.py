"""DocumentIR — the unified intermediate representation for Translayer.

This is the core open-standard artifact: any format is parsed *into* this
structure, and rendered *back out* of it. The most valuable asset is not the
text itself but the metadata surrounding it (semantic role, constraints,
write-back coordinates, term hits, and in-image text regions).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "0.1.0"


# --------------------------------------------------------------------------- #
# Text & formatting primitives
# --------------------------------------------------------------------------- #
class Font(BaseModel):
    name: str | None = None
    size: float | None = None  # points
    color: str | None = None  # #RRGGBB
    bold: bool = False
    italic: bool = False
    underline: bool = False


class Run(BaseModel):
    """Smallest rich-text unit; preserves inline formatting."""

    text: str
    font: Font = Field(default_factory=Font)
    lang: str | None = None


# --------------------------------------------------------------------------- #
# Layout & constraints
# --------------------------------------------------------------------------- #
class Position(BaseModel):
    """Box position. For PPTX, units are EMU (914400 EMU == 1 inch)."""

    x: int
    y: int
    w: int
    h: int


class Layout(BaseModel):
    slide_index: int = 0
    shape_id: int = 0
    page_index: int = 0
    element_id: str | None = None
    position: Position | None = None
    base_font: Font = Field(default_factory=Font)
    wrap: bool = True
    autofit: Literal["none", "shrink", "resize"] = "none"


class Constraints(BaseModel):
    max_chars: int | None = None
    can_shrink_font: bool = True
    min_font_size: float = 8.0
    max_lines: int | None = None


class TermHit(BaseModel):
    term: str
    preferred: str
    start: int
    end: int


# --------------------------------------------------------------------------- #
# Write-back addressing
# --------------------------------------------------------------------------- #
class SourceRef(BaseModel):
    """Precise, lossless write-back coordinate."""

    kind: Literal[
        "shape_text", "table_cell", "image_region",
        "paragraph", "heading", "list_item",
        "html_element", "html_attr", "html_image",
        "smartart_point",
    ]
    slide_index: int
    shape_id: int
    paragraph_index: int | None = None
    run_index: int | None = None
    row: int | None = None
    col: int | None = None
    image_id: str | None = None
    region_id: str | None = None


# --------------------------------------------------------------------------- #
# Blocks
# --------------------------------------------------------------------------- #
BlockType = Literal[
    "title", "subtitle", "body", "list_item", "table_cell", "shape_text", "image",
    "heading", "paragraph", "smartart",
]


class Block(BaseModel):
    id: str
    type: BlockType
    semantic_role: str | None = None  # title/body/caption/footer/watermark...
    runs: list[Run] = Field(default_factory=list)
    source_text: str = ""
    target_text: str | None = None
    translatable: bool = True
    layout: Layout | None = None
    constraints: Constraints = Field(default_factory=Constraints)
    term_hits: list[TermHit] = Field(default_factory=list)
    source_ref: SourceRef


# --------------------------------------------------------------------------- #
# Image resources & in-image text
# --------------------------------------------------------------------------- #
class ImageTextRegion(BaseModel):
    id: str
    bbox: Position
    polygon: list[tuple[int, int]] | None = None
    source_text: str
    target_text: str | None = None
    font_estimate: Font = Field(default_factory=Font)
    align: Literal["left", "center", "right"] = "left"
    background_kind: Literal["solid", "gradient", "photo"] = "solid"
    translatable: bool = True


class ImageResource(BaseModel):
    id: str
    media_type: str  # image/png ...
    data_ref: str  # path to the extracted original image
    width: int
    height: int
    text_regions: list[ImageTextRegion] = Field(default_factory=list)
    localized_data_ref: str | None = None  # path to re-drawn localized image


class FontRef(BaseModel):
    name: str
    embedded: bool = False
    data_ref: str | None = None


class Resources(BaseModel):
    fonts: list[FontRef] = Field(default_factory=list)
    images: list[ImageResource] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Document
# --------------------------------------------------------------------------- #
class DocMeta(BaseModel):
    source_lang: str
    target_lang: str
    doc_type: str = "pptx"
    title: str | None = None
    glossary_ref: str | None = None
    engine_hints: dict = Field(default_factory=dict)


class DocumentIR(BaseModel):
    schema_version: str = SCHEMA_VERSION
    meta: DocMeta
    resources: Resources = Field(default_factory=Resources)
    blocks: list[Block] = Field(default_factory=list)

    def translatable_blocks(self) -> list[Block]:
        return [b for b in self.blocks if b.translatable and b.source_text.strip()]

    def block_by_id(self, block_id: str) -> Block | None:
        return next((b for b in self.blocks if b.id == block_id), None)

    def image_by_id(self, image_id: str) -> ImageResource | None:
        return next((im for im in self.resources.images if im.id == image_id), None)
