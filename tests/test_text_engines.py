from __future__ import annotations

from translayer.engines import translation as _translation  # noqa: F401
from translayer.plugins import registry


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, response_payload, calls, **_kwargs):
        self.response_payload = response_payload
        self.calls = calls

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _FakeResponse(self.response_payload)


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


def test_openai_compatible_engine_uses_job_url_key_and_model(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "translayer.engines.translation.openai_engine.httpx.Client",
        lambda **kwargs: _FakeClient(
            {"choices": [{"message": {"content": '["你好"]'}}]}, calls, **kwargs
        ),
    )
    engine = registry.get(
        "translation",
        "openai",
        base_url="http://llm.internal:8000/v1",
        api_key="local-secret",
        model="local-model",
    )

    assert engine.translate(["Hello"], "en", "zh") == ["你好"]
    url, request = calls[0]
    assert url == "http://llm.internal:8000/v1/chat/completions"
    assert request["headers"] == {"Authorization": "Bearer local-secret"}
    assert request["json"]["model"] == "local-model"


def test_openai_compatible_engine_allows_authless_local_api(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "translayer.engines.translation.openai_engine.httpx.Client",
        lambda **kwargs: _FakeClient(
            {"choices": [{"message": {"content": '["Hallo"]'}}]}, calls, **kwargs
        ),
    )
    engine = registry.get(
        "translation",
        "openai",
        base_url="http://localhost:11434/v1/chat/completions",
        api_key="",
        model="example-model",
    )

    assert engine.translate(["Hello"], "en", "de") == ["Hallo"]
    assert calls[0][1]["headers"] == {}


def test_openai_compatible_engine_adapts_moonshot_kimi_reasoning_model(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "translayer.engines.translation.openai_engine.httpx.Client",
        lambda **kwargs: _FakeClient(
            {"choices": [{"message": {"content": '["Hallo"]'}}]}, calls, **kwargs
        ),
    )
    engine = registry.get(
        "translation",
        "openai",
        base_url="https://api.moonshot.cn/v1",
        api_key="moonshot-key",
        model="kimi-k2.6",
    )

    assert engine.translate(["你好"], "zh", "de") == ["Hallo"]
    request_json = calls[0][1]["json"]
    assert "temperature" not in request_json
    assert request_json["thinking"] == {"type": "disabled"}


def test_deepl_engine_uses_current_json_and_header_format(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "translayer.engines.translation.deepl_engine.httpx.Client",
        lambda **kwargs: _FakeClient(
            {"translations": [{"text": "Hallo"}]}, calls, **kwargs
        ),
    )
    engine = registry.get("translation", "deepl", api_key="test-key:fx")

    assert engine.translate(["Hello"], "en", "de", context="Greeting") == ["Hallo"]
    url, request = calls[0]
    assert url == "https://api-free.deepl.com/v2/translate"
    assert request["headers"] == {"Authorization": "DeepL-Auth-Key test-key:fx"}
    assert request["json"] == {
        "source_lang": "EN",
        "target_lang": "DE",
        "text": ["Hello"],
        "context": "Greeting",
    }
