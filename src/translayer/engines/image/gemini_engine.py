"""Gemini native image-editing adapter for text localization."""

from __future__ import annotations

import base64
import io
import os
from typing import Any

from PIL import Image

from translayer.config import settings
from translayer.plugins import registry

_LANGUAGE_NAMES = {
    "zh": "Simplified Chinese (zh-CN)",
    "zh-cn": "Simplified Chinese (zh-CN)",
    "de": "German (de-DE)",
    "de-de": "German (de-DE)",
    "en": "English",
}


def _language_name(code: str) -> str:
    return _LANGUAGE_NAMES.get(code.lower(), code)


@registry.register("image_localization", "gemini")
class GeminiImageLocalizationEngine:
    """Use Gemini native image editing to translate every embedded text label."""

    name = "gemini"

    def __init__(self, client: Any | None = None):
        self._client = client

    def localize(self, image_path: str, out_path: str, src: str, tgt: str) -> str:
        with Image.open(image_path) as original:
            original_size = original.size
            original_format = original.format or "PNG"

        with open(image_path, "rb") as image_file:
            image_bytes = image_file.read()

        client = self._client or self._create_client()
        interaction = client.interactions.create(
            model=settings.gemini_image_model,
            input=[
                {
                    "type": "image",
                    "data": base64.b64encode(image_bytes).decode("ascii"),
                    "mime_type": _mime_type(image_path),
                },
                {"type": "text", "text": self.build_prompt(src, tgt)},
            ],
            # The Interactions API currently accepts JPEG for native image edits.
            # We normalize the returned bytes to the caller's requested format below.
            response_format={"type": "image", "mime_type": "image/jpeg"},
        )

        output_image = getattr(interaction, "output_image", None)
        encoded = getattr(output_image, "data", None)
        if not encoded:
            raise RuntimeError("Gemini returned no edited image")

        try:
            generated = Image.open(io.BytesIO(base64.b64decode(encoded)))
            generated.load()
        except Exception as exc:  # noqa: BLE001 - normalize SDK/decoding failures
            raise RuntimeError("Gemini returned invalid image data") from exc

        if generated.size != original_size:
            generated = generated.resize(original_size, Image.Resampling.LANCZOS)

        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        _save_for_path(generated, out_path, original_format)
        return out_path

    @staticmethod
    def build_prompt(src: str, tgt: str) -> str:
        source = _language_name(src)
        target = _language_name(tgt)
        return f"""Edit the provided image as a professional document-localization task.

Translate every legible natural-language text element from {source} into {target}.
Render each translation directly where the original text appears, matching its visual role,
alignment, hierarchy, color, and style. Make translated text readable and correctly spelled.

Preserve all non-text visual content exactly: composition, background, illustrations, people,
objects, diagrams, connectors, chart geometry, numbers, units, product names, company names,
acronyms, and logos. Do not translate brand marks such as SAP, BOMB AI, or KraussMaffei.

Do not add a white box, text box, panel, label, banner, border, solid color block, background
plate, callout container, or any new graphic element. Text that was printed directly on the
background must remain printed directly on that background. Return only the edited image."""

    def _create_client(self) -> Any:
        if not settings.gemini_api_key:
            raise RuntimeError(
                "Gemini image localization requires GEMINI_API_KEY (or GOOGLE_API_KEY)"
            )
        try:
            from google import genai
        except ImportError as exc:
            raise RuntimeError(
                "Gemini image localization is optional. Install it with "
                "`pip install 'translayer[gemini]'`."
            ) from exc
        return genai.Client(api_key=settings.gemini_api_key)


def _mime_type(path: str) -> str:
    suffix = os.path.splitext(path)[1].lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(suffix, "image/png")


def _save_for_path(image: Image.Image, out_path: str, original_format: str) -> None:
    suffix = os.path.splitext(out_path)[1].lower()
    if suffix in {".jpg", ".jpeg"}:
        image.convert("RGB").save(out_path, format="JPEG", quality=95)
        return
    if suffix == ".webp":
        image.save(out_path, format="WEBP", quality=95)
        return
    target_format = "PNG" if suffix == ".png" else original_format
    if target_format.upper() in {"JPEG", "JPG"}:
        image = image.convert("RGB")
    image.save(out_path, format=target_format)
