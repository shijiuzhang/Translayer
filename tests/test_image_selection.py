from __future__ import annotations

import shutil

from PIL import Image

from translayer.engines.image.cost_guard import ImageAPICostGuard
from translayer.enrich.image_selection import (
    ImageSelector,
    ProbeResult,
    ProbeWord,
    plan_payload,
)
from translayer.ir.models import DocMeta, DocumentIR, ImageResource, Resources


class _FakeProbe:
    def __init__(self, results: dict[str, ProbeResult]):
        self.results = results
        self.calls: list[str] = []

    def probe(self, image_path: str) -> ProbeResult:
        self.calls.append(image_path)
        return self.results[image_path]


def _word(text: str, line: int, confidence: float = 90.0) -> ProbeWord:
    return ProbeWord(text, confidence, 10, line * 25, 80, 20, 1, 1, line)


def _resource(identifier: str, path: str, width: int = 800, height: int = 600):
    return ImageResource(
        id=identifier,
        media_type="image/png",
        data_ref=path,
        width=width,
        height=height,
    )


def test_selector_routes_text_images_and_exact_duplicates(tmp_path) -> None:
    rich = tmp_path / "rich.png"
    duplicate = tmp_path / "duplicate.png"
    simple = tmp_path / "simple.png"
    empty = tmp_path / "empty.png"
    tiny = tmp_path / "tiny.png"
    Image.new("RGB", (800, 600), "white").save(rich)
    shutil.copyfile(rich, duplicate)
    Image.new("RGB", (800, 600), "blue").save(simple)
    Image.new("RGB", (800, 600), "black").save(empty)
    Image.new("RGB", (32, 32), "red").save(tiny)

    rich_words = tuple(
        _word(text, line)
        for line, text in enumerate(
            [
                "Enterprise",
                "artificial",
                "intelligence",
                "requires",
                "governance",
                "secure",
                "business",
                "workflows",
            ],
            1,
        )
    )
    probe = _FakeProbe(
        {
            str(rich): ProbeResult(rich_words),
            str(simple): ProbeResult((_word("Revenue", 1),)),
            str(empty): ProbeResult(()),
        }
    )
    ir = DocumentIR(
        meta=DocMeta(source_lang="en", target_lang="zh"),
        resources=Resources(
            images=[
                _resource("rich", str(rich)),
                _resource("duplicate", str(duplicate)),
                _resource("simple", str(simple)),
                _resource("empty", str(empty)),
                _resource("tiny", str(tiny), 32, 32),
            ]
        ),
    )

    analyses = ImageSelector(probe=probe, cache_dir=tmp_path / "cache").analyze(ir)

    assert [analysis.route for analysis in analyses] == [
        "whole_image",
        "reuse",
        "region",
        "skip",
        "skip",
    ]
    assert analyses[1].duplicate_of == "rich"
    assert str(duplicate) not in probe.calls
    assert str(tiny) not in probe.calls


def test_plan_estimates_only_unique_whole_image_calls(tmp_path) -> None:
    image_path = tmp_path / "image.png"
    Image.new("RGB", (800, 600), "white").save(image_path)
    probe = _FakeProbe(
        {
            str(image_path): ProbeResult(
                tuple(
                    _word(word, line)
                    for line, word in enumerate(
                        "enterprise artificial intelligence requires governed secure business data workflows".split(),
                        1,
                    )
                )
            )
        }
    )
    ir = DocumentIR(
        meta=DocMeta(source_lang="en", target_lang="zh"),
        resources=Resources(images=[_resource("image", str(image_path))]),
    )
    ImageSelector(probe=probe).analyze(ir)

    payload = plan_payload(ir, ["zh", "de"], estimated_cost_per_image=0.08, budget_usd=0.10)

    assert payload["provider_calls_made"] == 0
    assert payload["summary"]["projected_paid_calls"] == 2
    assert payload["summary"]["estimated_total_cost_usd"] == 0.16
    assert payload["summary"]["within_budget"] is False


def test_selector_does_not_promote_ocr_noise_to_paid_route(tmp_path) -> None:
    image_path = tmp_path / "noisy.png"
    Image.new("RGB", (800, 600), "white").save(image_path)
    noisy = "a i x 1 rr ee q z CAD 7 ui m n"
    probe = _FakeProbe(
        {
            str(image_path): ProbeResult(
                tuple(_word(word, line) for line, word in enumerate(noisy.split(), 1))
            )
        }
    )
    ir = DocumentIR(
        meta=DocMeta(source_lang="en", target_lang="zh"),
        resources=Resources(images=[_resource("noisy", str(image_path))]),
    )

    analysis = ImageSelector(probe=probe).analyze(ir)[0]

    assert analysis.route == "review"
    assert analysis.reason == "ocr_noise"


def test_cost_guard_requires_explicit_bounded_budget() -> None:
    disabled = ImageAPICostGuard(enabled=False, max_calls=1, max_cost_usd=0.10)
    try:
        disabled.reserve()
    except RuntimeError as exc:
        assert "disabled" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("disabled guard should block")

    guard = ImageAPICostGuard(enabled=True, max_calls=1, max_cost_usd=0.10)
    guard.reserve()
    assert guard.calls_reserved == 1
    try:
        guard.reserve()
    except RuntimeError as exc:
        assert "limit" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("call limit should block")
