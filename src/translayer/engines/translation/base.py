"""Shared helpers for translation engines."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import TypeVar

T = TypeVar("T")


class BaseTranslationEngine(ABC):
    """Base class with common prompt, parsing, and batch helpers."""

    name: str

    @abstractmethod
    def translate(
        self,
        texts: list[str],
        src: str,
        tgt: str,
        context: str | None = None,
        glossary: dict[str, str] | None = None,
        max_chars: list[int | None] | None = None,
    ) -> list[str]: ...

    def build_prompt(
        self,
        texts: list[str],
        src: str,
        tgt: str,
        context: str | None = None,
        glossary: dict[str, str] | None = None,
        max_chars: list[int | None] | None = None,
    ) -> str:
        """Build a JSON-array translation prompt for a full batch."""
        parts = [
            f"Translate the following JSON array of strings from {src} to {tgt}.",
            "Return only a valid JSON array of strings with exactly the same length and order.",
        ]
        if context:
            parts.append(f"Use this whole-document context when choosing wording:\n{context}")
        if glossary:
            parts.append(
                "Obey this glossary term map exactly where applicable:\n"
                f"{json.dumps(glossary, ensure_ascii=False)}"
            )
        normalized_limits = self.normalize_max_chars(len(texts), max_chars)
        constraints = [
            {"index": index, "max_chars": limit}
            for index, limit in enumerate(normalized_limits)
            if limit is not None
        ]
        if constraints:
            parts.append(
                "Aim for these per-item translated character counts when natural:\n"
                f"{json.dumps(constraints, ensure_ascii=False)}"
                "\nTreat these as layout guidance. Never cut a word, return a fragment, "
                "or omit required meaning just to meet a character count."
            )
        parts.append(json.dumps(texts, ensure_ascii=False))
        return "\n\n".join(parts)

    @staticmethod
    def normalize_max_chars(
        count: int, max_chars: list[int | None] | None
    ) -> list[int | None]:
        """Pad or trim max-character constraints to match a batch length."""
        if max_chars is None:
            return [None] * count
        return (list(max_chars) + [None] * count)[:count]

    @staticmethod
    def apply_glossary(text: str, glossary: dict[str, str] | None) -> str:
        """Apply simple source-term to target-term replacements."""
        if not glossary:
            return text
        result = text
        for source, target in glossary.items():
            result = result.replace(source, target)
        return result

    def apply_glossary_to_many(
        self, texts: Iterable[str], glossary: dict[str, str] | None
    ) -> list[str]:
        """Apply glossary replacements to a sequence of strings."""
        return [self.apply_glossary(text, glossary) for text in texts]

    def enforce_max_chars(
        self, texts: list[str], max_chars: list[int | None] | None
    ) -> list[str]:
        """Keep complete translations; character limits are prompt-level guidance.

        Cutting by Python string index produced broken words such as
        ``collaborati`` and discarded meaning before human review. Layout fitting
        is responsible for adapting complete translations to their containers.
        """
        self.normalize_max_chars(len(texts), max_chars)
        return list(texts)

    @staticmethod
    def chunk_batch(items: list[T], chunk_size: int) -> list[list[T]]:
        """Split a list into ordered chunks."""
        if chunk_size <= 0:
            raise ValueError("chunk_size must be greater than zero")
        return [items[index : index + chunk_size] for index in range(0, len(items), chunk_size)]

    @staticmethod
    def join_batches(batches: Iterable[Iterable[T]]) -> list[T]:
        """Flatten ordered batches into a single list."""
        return [item for batch in batches for item in batch]

    def parse_json_array_response(self, content: str, expected_len: int, fallback: list[str]) -> list[str]:
        """Parse a model response into a string list, falling back to originals on failure."""
        candidates = [content.strip()]
        if "```" in content:
            fenced = content.split("```")
            candidates.extend(part.removeprefix("json").strip() for part in fenced[1::2])
        start = content.find("[")
        end = content.rfind("]")
        if start != -1 and end > start:
            candidates.append(content[start : end + 1])

        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, list):
                values = [item if isinstance(item, str) else str(item) for item in parsed]
                if len(values) == expected_len:
                    return values
                if values:
                    return (values + fallback)[:expected_len]

        lines = [line.strip(" -\t\r\n\"'") for line in content.splitlines() if line.strip()]
        if len(lines) == expected_len:
            return lines
        return fallback[:expected_len]
