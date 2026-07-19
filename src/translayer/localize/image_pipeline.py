"""Image localization sub-pipeline (Route A).

For each image: translate the OCR-detected regions (with document context),
erase the original text via the inpaint engine, then redraw the translations
with a real target-language font sized to fit each region. The localized image
is written next to the original and referenced via ``localized_data_ref``.

A VLM self-check hook is stubbed for a future quality loop.
"""

from __future__ import annotations

import os

from PIL import Image

from translayer.fonts import layout as font_layout
from translayer.ir.models import DocumentIR, ImageResource
from translayer.plugins import registry


def _verify_region(_image_path: str, _region) -> bool:
    """VLM self-check stub — always passes for the MVP."""
    return True


def localize_images(
    ir: DocumentIR,
    translation_engine: str = "openai",
    inpaint_engine: str = "pillow",
) -> DocumentIR:
    images = [
        image
        for image in ir.resources.images
        if image.text_regions
        and not image.localized_data_ref
        and (image.selection is None or image.selection.route == "region")
    ]
    if not images:
        return ir

    translator = registry.get("translation", translation_engine)
    inpainter = registry.get("inpaint", inpaint_engine)
    src, tgt = ir.meta.source_lang, ir.meta.target_lang

    for image in images:
        _localize_one(image, translator, inpainter, src, tgt)
    return ir


def _localize_one(image: ImageResource, translator, inpainter, src: str, tgt: str) -> None:
    regions = [r for r in image.text_regions if r.translatable and r.source_text.strip()]
    if not regions:
        return

    # 1. Translate region texts together (shared image context).
    texts = [r.source_text for r in regions]
    context = " / ".join(texts)
    max_chars = [None] * len(texts)
    translations = translator.translate(
        texts, src=src, tgt=tgt, context=context, max_chars=max_chars
    )
    for region, translated in zip(regions, translations, strict=False):
        region.target_text = translated

    # 2. Erase original text.
    base, ext = os.path.splitext(image.data_ref)
    erased_path = f"{base}.erased{ext or '.png'}"
    inpainter.erase(image.data_ref, regions, erased_path)

    # 3. Redraw translations with a real font sized to fit each region.
    img = Image.open(erased_path).convert("RGB")
    for region in regions:
        font_layout.render_text_in_box(img, region, lang=tgt)
        _verify_region(erased_path, region)

    out_path = f"{base}.localized{ext or '.png'}"
    img.save(out_path)
    image.localized_data_ref = out_path
