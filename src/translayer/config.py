"""Runtime configuration via environment variables.

All engines are adapters; defaults point at cloud providers but every choice is
overridable so cloud and local backends are interchangeable.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


@dataclass
class Settings:
    # Default engine selection (adapter keys in the registry)
    translation_engine: str = field(default_factory=lambda: _env("TRANSLAYER_TRANSLATION", "openai"))
    ocr_engine: str = field(default_factory=lambda: _env("TRANSLAYER_OCR", "cloud_vision"))
    inpaint_engine: str = field(default_factory=lambda: _env("TRANSLAYER_INPAINT", "pillow"))

    # OpenAI-compatible translation backend
    openai_api_key: str = field(default_factory=lambda: _env("OPENAI_API_KEY"))
    openai_base_url: str = field(default_factory=lambda: _env("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    openai_model: str = field(default_factory=lambda: _env("TRANSLAYER_OPENAI_MODEL", "gpt-4o-mini"))

    # DeepL
    deepl_api_key: str = field(default_factory=lambda: _env("DEEPL_API_KEY"))

    # Cloud vision OCR (OpenAI-compatible vision)
    vision_api_key: str = field(default_factory=lambda: _env("OPENAI_API_KEY"))
    vision_base_url: str = field(default_factory=lambda: _env("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    vision_model: str = field(default_factory=lambda: _env("TRANSLAYER_VISION_MODEL", "gpt-4o"))

    # Storage
    jobs_dir: str = field(default_factory=lambda: _env("TRANSLAYER_JOBS_DIR", ".translayer_jobs"))


settings = Settings()
