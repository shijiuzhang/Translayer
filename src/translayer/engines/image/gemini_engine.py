"""Gemini native image-editing adapter for text localization."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
from typing import Any

from PIL import Image

from translayer.config import settings
from translayer.engines.image.cost_guard import ImageAPICostGuard
from translayer.languages import language_name
from translayer.plugins import registry

_PROMPT_VERSION = "localize-v3-explicit-text-map"

@registry.register("image_localization", "gemini")
class GeminiImageLocalizationEngine:
    """Use Gemini native image editing to translate every embedded text label."""

    name = "gemini"

    def __init__(
        self,
        client: Any | None = None,
        cost_guard: ImageAPICostGuard | None = None,
        cache_dir: str | None = None,
    ):
        self._client = client
        self._cost_guard = cost_guard or ImageAPICostGuard(
            enabled=settings.gemini_image_api_enabled,
            max_calls=settings.gemini_image_max_calls,
            max_cost_usd=settings.gemini_image_budget_usd,
            estimated_cost_per_call_usd=settings.gemini_image_estimated_cost_usd,
        )
        self._cache_dir = cache_dir or settings.gemini_image_cache_dir

    def localize(
        self,
        image_path: str,
        out_path: str,
        src: str,
        tgt: str,
        text_mappings: list[tuple[str, str]] | None = None,
    ) -> str:
        with Image.open(image_path) as original:
            original_size = original.size
            original_format = original.format or "PNG"

        with open(image_path, "rb") as image_file:
            image_bytes = image_file.read()

        cache_path = self._cache_path(image_bytes, src, tgt, text_mappings)
        if os.path.exists(cache_path):
            os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
            with Image.open(cache_path) as cached:
                cached.load()
                _save_for_path(cached, out_path, original_format)
            return out_path

        # This is the only point at which a paid provider request can be made.
        # Cache hits above never reserve budget or call the provider.
        self._cost_guard.reserve()
        client = self._client or self._create_client()
        interaction = client.interactions.create(
            model=settings.gemini_image_model,
            input=[
                {
                    "type": "image",
                    "data": base64.b64encode(image_bytes).decode("ascii"),
                    "mime_type": _mime_type(image_path),
                },
                {"type": "text", "text": self.build_prompt(src, tgt, text_mappings)},
            ],
            # The Interactions API currently accepts JPEG for native image edits.
            # We normalize the returned bytes to the caller's requested format below.
            response_format={"type": "image", "mime_type": "image/jpeg"},
        )

        encoded = _final_output_image_data(interaction)
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
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        generated.save(cache_path, format="PNG")
        return out_path

    def _cache_path(
        self,
        image_bytes: bytes,
        src: str,
        tgt: str,
        text_mappings: list[tuple[str, str]] | None = None,
    ) -> str:
        digest = hashlib.sha256()
        digest.update(image_bytes)
        digest.update(settings.gemini_image_model.encode("utf-8"))
        digest.update(src.lower().encode("utf-8"))
        digest.update(tgt.lower().encode("utf-8"))
        digest.update(_PROMPT_VERSION.encode("utf-8"))
        digest.update(
            json.dumps(text_mappings or [], ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
        )
        return os.path.join(self._cache_dir, f"{digest.hexdigest()}.png")

    def invalidate_cache(
        self,
        image_path: str,
        src: str,
        tgt: str,
        text_mappings: list[tuple[str, str]] | None = None,
    ) -> None:
        """Remove a generated result rejected by post-generation quality checks."""

        with open(image_path, "rb") as image_file:
            image_bytes = image_file.read()
        cache_path = self._cache_path(image_bytes, src, tgt, text_mappings)
        if os.path.exists(cache_path):
            os.remove(cache_path)

    @staticmethod
    def build_prompt(
        src: str,
        tgt: str,
        text_mappings: list[tuple[str, str]] | None = None,
    ) -> str:
        source = language_name(src)
        target = language_name(tgt)
        mapping_instructions = ""
        if text_mappings:
            mapping_instructions = f"""

The OCR and translation stages produced this mandatory replacement list:
{json.dumps(
    [{"source": source_text, "target": target_text} for source_text, target_text in text_mappings],
    ensure_ascii=False,
    indent=2,
)}

Replace every listed source string exactly once with its paired target string. A heading, label,
button, caption, axis title, or text inside a decorative shape is still text and must be replaced.
Never preserve a listed source string because it resembles a graphic, title, brand, or design
element. Preserve a brand only when its source and target values in the list are identical.
"""
        return f"""Edit the provided image as a professional document-localization task.

Translate every legible natural-language text element from {source} into {target}.
Render each translation directly where the original text appears, matching its visual role,
alignment, hierarchy, color, and style. Make translated text readable and correctly spelled.
{mapping_instructions}

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


def _final_output_image_data(interaction: Any) -> str | None:
    """Read the final image without ever accepting an interim thought image."""

    output_image = getattr(interaction, "output_image", None)
    encoded = getattr(output_image, "data", None)
    if encoded:
        return encoded
    for step in reversed(getattr(interaction, "steps", None) or []):
        if getattr(step, "type", None) != "model_output":
            continue
        for block in reversed(getattr(step, "content", None) or []):
            if getattr(block, "type", None) == "image" and getattr(block, "data", None):
                return block.data
    return None


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
