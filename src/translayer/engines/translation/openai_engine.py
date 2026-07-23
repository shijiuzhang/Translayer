"""OpenAI-compatible chat-completions translation engine."""

from __future__ import annotations

from typing import Any

import httpx

from translayer.config import settings
from translayer.engines.translation.base import BaseTranslationEngine
from translayer.plugins import registry


@registry.register("translation", "openai")
class OpenAIEngine(BaseTranslationEngine):
    """Translate batches with an OpenAI-compatible Chat Completions API."""

    name = "openai"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self.api_key = settings.openai_api_key if api_key is None else api_key.strip()
        self.base_url = (base_url or settings.openai_base_url).strip().rstrip("/")
        self.model = (model or settings.openai_model).strip()
        if not self.base_url:
            raise ValueError("OpenAI-compatible base URL is required")
        if not self.model:
            raise ValueError("OpenAI-compatible model name is required")
        if not self.base_url.startswith(("http://", "https://")):
            raise ValueError("OpenAI-compatible base URL must use http:// or https://")

    def translate(
        self,
        texts: list[str],
        src: str,
        tgt: str,
        context: str | None = None,
        glossary: dict[str, str] | None = None,
        max_chars: list[int | None] | None = None,
    ) -> list[str]:
        if not texts:
            return []

        prompt = self.build_prompt(texts, src, tgt, context, glossary, max_chars)
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a precise translation engine. Return only JSON, with no prose."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        }
        if self._is_moonshot_kimi_reasoning_model():
            payload["thinking"] = {"type": "disabled"}
        else:
            payload["temperature"] = 0
        endpoint = (
            self.base_url
            if self.base_url.endswith("/chat/completions")
            else f"{self.base_url}/chat/completions"
        )
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

        with httpx.Client(timeout=60) as client:
            response = client.post(endpoint, json=payload, headers=headers)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = response.text.strip()
                message = f"{exc} Response body: {detail}" if detail else str(exc)
                raise RuntimeError(message) from exc
            data = response.json()

        content = data["choices"][0]["message"].get("content", "")
        fallback = self.enforce_max_chars(self.apply_glossary_to_many(texts, glossary), max_chars)
        parsed = self.parse_json_array_response(content, len(texts), fallback)
        parsed = self.apply_glossary_to_many(parsed, glossary)
        return self.enforce_max_chars(parsed, max_chars)

    def _is_moonshot_kimi_reasoning_model(self) -> bool:
        base_url = self.base_url.lower()
        model = self.model.lower()
        return "moonshot." in base_url and model.startswith(("kimi-k2.5", "kimi-k2.6"))
