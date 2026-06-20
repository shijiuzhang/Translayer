from __future__ import annotations

from translayer.engines import translation as _translation  # noqa: F401
from translayer.plugins import registry


def test_mock_engine_batch_length_preserved():
    engine = registry.get("translation", "mock")

    result = engine.translate(["Hello", "World"], "en", "zh")

    assert result == ["[zh] Hello", "[zh] World"]


def test_mock_engine_glossary_applied():
    engine = registry.get("translation", "mock")

    result = engine.translate(["Hello world"], "en", "zh", glossary={"Hello": "你好"})

    assert result == ["[zh] 你好 world"]


def test_mock_engine_max_chars_respected():
    engine = registry.get("translation", "mock")

    result = engine.translate(["abcdef", "abcdef"], "en", "zh", max_chars=[5, None])

    assert result == ["[zh] ", "[zh] abcdef"]
    assert len(result[0]) <= 5


def test_registry_get_mock_returns_working_engine():
    engine = registry.get("translation", "mock")

    assert engine.name == "mock"
    assert engine.translate(["Text"], "en", "de") == ["[de] Text"]


def test_registry_discover_makes_translation_engines_available():
    registry.discover()

    available = registry.available("translation")
    assert "openai" in available
    assert "deepl" in available
    assert "mock" in available
