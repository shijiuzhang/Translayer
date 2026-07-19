from __future__ import annotations

import base64
import io
from types import SimpleNamespace

import pytest
from PIL import Image

from translayer.config import settings
from translayer.engines.image.cost_guard import ImageAPICostGuard
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
    engine = GeminiImageLocalizationEngine(
        client=client,
        cost_guard=ImageAPICostGuard(enabled=True, max_calls=1, max_cost_usd=0.10),
        cache_dir=str(tmp_path / "cache"),
    )

    mappings = [("The Trap", "Die Falle")]
    assert engine.localize(
        str(source), str(output), "en", "de", text_mappings=mappings
    ) == str(output)
    assert Image.open(output).size == (320, 180)
    assert interactions.kwargs["model"] == settings.gemini_image_model
    assert interactions.kwargs["response_format"]["mime_type"] == "image/jpeg"
    prompt = interactions.kwargs["input"][1]["text"]
    assert "German (de-DE)" in prompt
    assert "Do not add a white box" in prompt
    assert "logos" in prompt
    assert '"source": "The Trap"' in prompt
    assert '"target": "Die Falle"' in prompt
    assert "heading, label" in prompt


def test_gemini_requires_api_key(monkeypatch, tmp_path) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (32, 32), "white").save(source)
    monkeypatch.setattr(settings, "gemini_api_key", "")

    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        GeminiImageLocalizationEngine(
            cost_guard=ImageAPICostGuard(enabled=True, max_calls=1, max_cost_usd=0.10),
            cache_dir=str(tmp_path / "cache"),
        ).localize(
            str(source), str(tmp_path / "out.png"), "en", "zh"
        )


def test_gemini_finds_final_image_in_model_output_steps(tmp_path) -> None:
    source = tmp_path / "source.png"
    output = tmp_path / "localized.png"
    Image.new("RGB", (320, 180), "white").save(source)
    final_data = _encoded_image((320, 180), "green")
    thought_data = _encoded_image((320, 180), "red")
    interaction = SimpleNamespace(
        output_image=None,
        steps=[
            SimpleNamespace(
                type="thought",
                summary=[SimpleNamespace(type="image", data=thought_data)],
            ),
            SimpleNamespace(
                type="model_output",
                content=[SimpleNamespace(type="image", data=final_data)],
            ),
        ],
    )
    interactions = SimpleNamespace(create=lambda **_kwargs: interaction)
    engine = GeminiImageLocalizationEngine(
        client=SimpleNamespace(interactions=interactions),
        cost_guard=ImageAPICostGuard(enabled=True, max_calls=1, max_cost_usd=0.10),
        cache_dir=str(tmp_path / "cache"),
    )

    engine.localize(str(source), str(output), "de", "en")

    assert Image.open(output).getpixel((0, 0)) == (0, 128, 0)


def test_gemini_paid_calls_are_disabled_by_default(tmp_path) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (32, 32), "white").save(source)

    with pytest.raises(RuntimeError, match="Paid image API calls are disabled"):
        GeminiImageLocalizationEngine(cache_dir=str(tmp_path / "cache")).localize(
            str(source), str(tmp_path / "out.png"), "en", "zh"
        )


def test_gemini_cache_avoids_a_second_provider_call(tmp_path) -> None:
    source = tmp_path / "source.png"
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    Image.new("RGB", (320, 180), "white").save(source)
    interactions = _FakeInteractions(_encoded_image((320, 180), "green"))
    guard = ImageAPICostGuard(enabled=True, max_calls=1, max_cost_usd=0.10)
    engine = GeminiImageLocalizationEngine(
        client=SimpleNamespace(interactions=interactions),
        cost_guard=guard,
        cache_dir=str(tmp_path / "cache"),
    )

    engine.localize(str(source), str(first), "en", "de")
    interactions.kwargs = None
    engine.localize(str(source), str(second), "en", "de")

    assert interactions.kwargs is None
    assert guard.calls_reserved == 1
    assert Image.open(second).size == (320, 180)


def test_gemini_cache_depends_on_explicit_text_map(tmp_path) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (320, 180), "white").save(source)
    interactions = _FakeInteractions(_encoded_image((320, 180), "green"))
    guard = ImageAPICostGuard(enabled=True, max_calls=2, max_cost_usd=0.20)
    engine = GeminiImageLocalizationEngine(
        client=SimpleNamespace(interactions=interactions),
        cost_guard=guard,
        cache_dir=str(tmp_path / "cache"),
    )

    engine.localize(
        str(source), str(tmp_path / "first.png"), "de", "en",
        text_mappings=[("Die Falle", "The Trap")],
    )
    engine.localize(
        str(source), str(tmp_path / "second.png"), "de", "en",
        text_mappings=[("Die Falle", "Pitfall")],
    )

    assert guard.calls_reserved == 2


def test_invalidating_rejected_gemini_result_forces_new_call(tmp_path) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (320, 180), "white").save(source)
    interactions = _FakeInteractions(_encoded_image((320, 180), "green"))
    guard = ImageAPICostGuard(enabled=True, max_calls=2, max_cost_usd=0.20)
    engine = GeminiImageLocalizationEngine(
        client=SimpleNamespace(interactions=interactions),
        cost_guard=guard,
        cache_dir=str(tmp_path / "cache"),
    )
    mappings = [("Die Falle", "The Trap")]

    engine.localize(
        str(source), str(tmp_path / "rejected.png"), "de", "en", mappings
    )
    engine.invalidate_cache(str(source), "de", "en", mappings)
    engine.localize(
        str(source), str(tmp_path / "retry.png"), "de", "en", mappings
    )

    assert guard.calls_reserved == 2


def test_gemini_image_engine_is_registered() -> None:
    registry.discover()
    assert "gemini" in registry.available("image_localization")


@pytest.mark.parametrize(
    ("source", "target", "source_name", "target_name"),
    [
        ("en", "zh", "English", "Simplified Chinese"),
        ("en", "de", "English", "German"),
        ("zh", "en", "Simplified Chinese", "English"),
        ("zh", "de", "Simplified Chinese", "German"),
        ("de", "en", "German", "English"),
        ("de", "zh", "German", "Simplified Chinese"),
    ],
)
def test_gemini_prompt_supports_every_language_direction(
    source: str, target: str, source_name: str, target_name: str
) -> None:
    prompt = GeminiImageLocalizationEngine.build_prompt(source, target)
    assert f"from {source_name}" in prompt
    assert f"into {target_name}" in prompt
