"""DeepL translation engine."""

from __future__ import annotations

import httpx

from translayer.config import settings
from translayer.engines.translation.base import BaseTranslationEngine
from translayer.languages import normalize_language
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

    def __init__(self, *, api_key: str | None = None, base_url: str | None = None) -> None:
        self.api_key = settings.deepl_api_key if api_key is None else api_key.strip()
        self.base_url = base_url.strip().rstrip("/") if base_url else None
        if self.base_url and not self.base_url.startswith(("http://", "https://")):
            raise ValueError("DeepL base URL must use http:// or https://")

    def translate(
        self,
        texts: list[str],
        src: str,
        tgt: str,
        context: str | None = None,
        glossary: dict[str, str] | None = None,
        max_chars: list[int | None] | None = None,
    ) -> list[str]:
        if not self.api_key:
            raise RuntimeError("DeepL translation engine requires DEEPL_API_KEY")
        if not texts:
            return []

        endpoint = self._endpoint(self.api_key, self.base_url)
        data = {
            "source_lang": self._lang(src),
            "target_lang": self._lang(tgt),
            "text": texts,
        }
        if context:
            data["context"] = context
        headers = {"Authorization": f"DeepL-Auth-Key {self.api_key}"}
        with httpx.Client(timeout=60) as client:
            response = client.post(endpoint, json=data, headers=headers)
            response.raise_for_status()
            payload = response.json()

        translated = [item["text"] for item in payload.get("translations", [])]
        if len(translated) != len(texts):
            translated = (translated + texts)[: len(texts)]
        translated = self.apply_glossary_to_many(translated, glossary)
        return self.enforce_max_chars(translated, max_chars)

    @staticmethod
    def _endpoint(api_key: str, base_url: str | None = None) -> str:
        if base_url:
            return base_url if base_url.endswith("/v2/translate") else f"{base_url}/v2/translate"
        if api_key.endswith(":fx"):
            return "https://api-free.deepl.com/v2/translate"
        return "https://api.deepl.com/v2/translate"

    @staticmethod
    def _lang(code: str) -> str:
        return _LANG_MAP[normalize_language(code)]
