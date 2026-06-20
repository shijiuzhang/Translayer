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

    def translate(
        self,
        texts: list[str],
        src: str,
        tgt: str,
        context: str | None = None,
        glossary: dict[str, str] | None = None,
        max_chars: list[int | None] | None = None,
    ) -> list[str]:
        if not settings.openai_api_key:
            raise RuntimeError("OpenAI translation engine requires OPENAI_API_KEY")
        if not texts:
            return []

        prompt = self.build_prompt(texts, src, tgt, context, glossary, max_chars)
        payload: dict[str, Any] = {
            "model": settings.openai_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a precise translation engine. Return only JSON, with no prose."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
        }
        base_url = settings.openai_base_url.rstrip("/")
        headers = {"Authorization": f"Bearer {settings.openai_api_key}"}

        with httpx.Client(timeout=60) as client:
            response = client.post(f"{base_url}/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"].get("content", "")
        fallback = self.enforce_max_chars(self.apply_glossary_to_many(texts, glossary), max_chars)
        parsed = self.parse_json_array_response(content, len(texts), fallback)
        parsed = self.apply_glossary_to_many(parsed, glossary)
        return self.enforce_max_chars(parsed, max_chars)
