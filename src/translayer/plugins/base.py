"""Plugin contracts for the four-stage pipeline.

Everything is pluggable: format plugins (Parser/Renderer), the enrichment
modules (Enricher) and the engines (Translation/OCR/Inpaint). New formats or
models are added as adapters without touching the core.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from translayer.ir.models import DocumentIR, ImageTextRegion


@runtime_checkable
class ParserPlugin(Protocol):
    name: str

    def supported_formats(self) -> list[str]: ...

    def parse(self, input_path: str, meta: dict) -> DocumentIR: ...


@runtime_checkable
class RendererPlugin(Protocol):
    name: str

    def supported_formats(self) -> list[str]: ...

    def render(self, ir: DocumentIR, input_path: str, output_path: str) -> None:
        """PPTX-like renderers need the original file for lossless write-back."""
        ...


@runtime_checkable
class EnricherPlugin(Protocol):
    name: str

    def enrich(self, ir: DocumentIR) -> DocumentIR: ...


@runtime_checkable
class TranslationEngine(Protocol):
    name: str

    def translate(
        self,
        texts: list[str],
        src: str,
        tgt: str,
        context: str | None = None,
        glossary: dict[str, str] | None = None,
        max_chars: list[int | None] | None = None,
    ) -> list[str]: ...


@runtime_checkable
class OCREngine(Protocol):
    name: str

    def detect(self, image_path: str) -> list[ImageTextRegion]: ...


@runtime_checkable
class InpaintEngine(Protocol):
    name: str

    def erase(
        self, image_path: str, regions: list[ImageTextRegion], out_path: str
    ) -> str: ...


@runtime_checkable
class ImageLocalizationEngine(Protocol):
    """Translate text embedded in a raster image and preserve its visual design."""

    name: str

    def localize(
        self,
        image_path: str,
        out_path: str,
        src: str,
        tgt: str,
        text_mappings: list[tuple[str, str]] | None = None,
    ) -> str: ...

    def invalidate_cache(
        self,
        image_path: str,
        src: str,
        tgt: str,
        text_mappings: list[tuple[str, str]] | None = None,
    ) -> None: ...
