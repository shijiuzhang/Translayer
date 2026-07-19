from __future__ import annotations

import base64
import io
from types import SimpleNamespace

import pytest
from PIL import Image

from translayer.config import settings
from translayer.engines.image.gemini_engine import GeminiImageLocalizationEngine
from translayer.plugins import registry


class _FakeInteractions:
    def __init__(self, output_data: str):
        self.output_data = output_data
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(output_image=SimpleNamespace(data=self.output_data))


def _encoded_image(size: tuple[int, int], color: str = "navy") -> str:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def test_gemini_localizes_and_restores_original_size(tmp_path) -> None:
    source = tmp_path / "source.png"
    output = tmp_path / "localized.png"
    Image.new("RGB", (320, 180), "white").save(source)

    interactions = _FakeInteractions(_encoded_image((1376, 768)))
    client = SimpleNamespace(interactions=interactions)
    engine = GeminiImageLocalizationEngine(client=client)

    assert engine.localize(str(source), str(output), "en", "de") == str(output)
    assert Image.open(output).size == (320, 180)
    assert interactions.kwargs["model"] == settings.gemini_image_model
    assert interactions.kwargs["response_format"]["mime_type"] == "image/jpeg"
    prompt = interactions.kwargs["input"][1]["text"]
    assert "German (de-DE)" in prompt
    assert "Do not add a white box" in prompt
    assert "logos" in prompt


def test_gemini_requires_api_key(monkeypatch, tmp_path) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (32, 32), "white").save(source)
    monkeypatch.setattr(settings, "gemini_api_key", "")

    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        GeminiImageLocalizationEngine().localize(
            str(source), str(tmp_path / "out.png"), "en", "zh"
        )


def test_gemini_image_engine_is_registered() -> None:
    registry.discover()
    assert "gemini" in registry.available("image_localization")
