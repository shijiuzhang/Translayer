"""DeepL translation engine."""

from __future__ import annotations

import httpx

from translayer.config import settings
from translayer.engines.translation.base import BaseTranslationEngine
from translayer.plugins import registry

_LANG_MAP = {
    "en": "EN",
    "zh": "ZH",
    "de": "DE",
}


@registry.register("translation", "deepl")
class DeepLEngine(BaseTranslationEngine):
    """Translate batches with the DeepL API."""

    name = "deepl"

    def translate(
        self,
        texts: list[str],
        src: str,
        tgt: str,
        context: str | None = None,
        glossary: dict[str, str] | None = None,
        max_chars: list[int | None] | None = None,
    ) -> list[str]:
        del context
        if not settings.deepl_api_key:
            raise RuntimeError("DeepL translation engine requires DEEPL_API_KEY")
        if not texts:
            return []

        endpoint = self._endpoint(settings.deepl_api_key)
        data = {
            "auth_key": settings.deepl_api_key,
            "source_lang": self._lang(src),
            "target_lang": self._lang(tgt),
            "text": texts,
        }
        with httpx.Client(timeout=60) as client:
            response = client.post(endpoint, data=data)
            response.raise_for_status()
            payload = response.json()

        translated = [item["text"] for item in payload.get("translations", [])]
        if len(translated) != len(texts):
            translated = (translated + texts)[: len(texts)]
        translated = self.apply_glossary_to_many(translated, glossary)
        return self.enforce_max_chars(translated, max_chars)

    @staticmethod
    def _endpoint(api_key: str) -> str:
        if api_key.endswith(":fx"):
            return "https://api-free.deepl.com/v2/translate"
        return "https://api.deepl.com/v2/translate"

    @staticmethod
    def _lang(code: str) -> str:
        return _LANG_MAP.get(code.lower(), code.upper())
