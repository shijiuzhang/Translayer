"""Canonical language metadata for the first supported translation matrix."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Language:
    code: str
    name: str
    pptx_tag: str
    tesseract: str
    paddle: str


LANGUAGES = {
    "en": Language("en", "English", "en-US", "eng", "en"),
    "de": Language("de", "German (de-DE)", "de-DE", "deu+eng", "german"),
    "zh": Language(
        "zh", "Simplified Chinese (zh-CN)", "zh-CN", "chi_sim+eng", "ch"
    ),
}

_ALIASES = {
    "en-us": "en",
    "en-gb": "en",
    "de-de": "de",
    "zh-cn": "zh",
    "zh-hans": "zh",
    "zh_hans": "zh",
}


def normalize_language(code: str) -> str:
    """Return an MVP language code or raise a useful validation error."""
    key = (code or "").strip().lower()
    key = _ALIASES.get(key, key)
    if key not in LANGUAGES:
        raise ValueError(
            f"unsupported language {code!r}; supported languages: en, de, zh"
        )
    return key


def language_name(code: str) -> str:
    return LANGUAGES[normalize_language(code)].name


def pptx_language_tag(code: str) -> str:
    return LANGUAGES[normalize_language(code)].pptx_tag


def tesseract_language(code: str) -> str:
    return LANGUAGES[normalize_language(code)].tesseract


def paddle_language(code: str) -> str:
    return LANGUAGES[normalize_language(code)].paddle
