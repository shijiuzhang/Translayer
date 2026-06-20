"""Deterministic translation engine for tests and local development."""

from __future__ import annotations

from translayer.engines.translation.base import BaseTranslationEngine
from translayer.plugins import registry


@registry.register("translation", "mock")
class MockEngine(BaseTranslationEngine):
    """Network-free deterministic engine."""

    name = "mock"

    def translate(
        self,
        texts: list[str],
        src: str,
        tgt: str,
        context: str | None = None,
        glossary: dict[str, str] | None = None,
        max_chars: list[int | None] | None = None,
    ) -> list[str]:
        del src, context
        translated = [f"[{tgt}] {self.apply_glossary(text, glossary)}" for text in texts]
        return self.enforce_max_chars(translated, max_chars)
