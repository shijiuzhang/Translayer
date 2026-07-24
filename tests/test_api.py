"""API tests via FastAPI TestClient using offline mock engines."""

from __future__ import annotations

import io
import time

from fastapi.testclient import TestClient

from translayer.api.app import app

client = TestClient(app)


def _wait_state(job_id: str, states: tuple[str, ...], timeout: float = 10.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/jobs/{job_id}").json()
        if job["state"] in states or job["state"] == "error":
            return job
        time.sleep(0.1)
    raise AssertionError(f"job did not reach one of {states}")


def test_index_served():
    r = client.get("/")
    assert r.status_code == 200
    assert "Translayer" in r.text
    assert '<html lang="en">' in r.text
    assert 'data-locale="en"' in r.text
    assert 'data-locale="de"' in r.text
    assert 'data-locale="zh"' in r.text
    assert "localStorage.getItem('translayer.locale')" in r.text
    assert 'id="translationApiUrl"' in r.text
    assert 'id="translationApiKey"' in r.text
    assert 'id="translationModel"' in r.text
    assert 'id="geminiApiKey"' in r.text
    assert 'id="clearCredentials"' in r.text
    assert "translayer.providerCredentials.v1" in r.text
    assert r.text.count("'credentials.local':") == 3
    assert r.text.count("'credentials.clear':") == 3
    assert r.text.count("'credentials.cleared':") == 3
    assert 'id="geminiCostPreview"' in r.text
    assert 'id="progressPanel"' in r.text
    assert 'role="progressbar"' in r.text


def test_public_configuration_exposes_cost_but_not_secrets(monkeypatch):
    monkeypatch.setattr("translayer.api.app.settings.gemini_api_key", "server-secret")
    response = client.get("/configuration")

    assert response.status_code == 200
    payload = response.json()
    assert payload["gemini_estimated_cost_per_image_usd"] > 0
    assert payload["gemini_key_configured_on_server"] is True
    assert "server-secret" not in response.text


def test_full_job_flow(sample_pptx):
    with open(sample_pptx, "rb") as fh:
        data = fh.read()
    r = client.post(
        "/jobs",
        files={"file": ("sample.pptx", io.BytesIO(data),
                         "application/vnd.openxmlformats-officedocument.presentationml.presentation")},
        data={"source_lang": "en", "target_lang": "zh", "translation_engine": "mock",
              "ocr_engine": "mock", "inpaint_engine": "pillow"},
    )
    assert r.status_code == 201
    job_id = r.json()["id"]

    job = _wait_state(job_id, ("image_review",))
    assert job["state"] == "image_review", job
    assert job["progress"]["text"]["completed"] == job["progress"]["text"]["total"]
    assert (
        job["progress"]["text"]["completed_items"]
        == job["progress"]["text"]["total_items"]
    )

    plan = client.get(f"/jobs/{job_id}/image-plan")
    assert plan.status_code == 200
    plan_data = plan.json()
    assert plan_data["summary"]["total_images"] == 1
    assert plan_data["summary"]["unresolved"] == 1
    assert plan_data["images"][0]["localization_validation"]["status"] == "not_run"

    image_id = plan_data["images"][0]["image_id"]
    preview = client.get(f"/jobs/{job_id}/images/{image_id}/preview")
    assert preview.status_code == 200
    assert client.post(f"/jobs/{job_id}/render").status_code == 409
    invalid_reuse = client.patch(
        f"/jobs/{job_id}/images/{image_id}/decision",
        json={"action": "reuse"},
    )
    assert invalid_reuse.status_code == 422

    decision = client.patch(
        f"/jobs/{job_id}/images/{image_id}/decision",
        json={"action": "preserve"},
    )
    assert decision.status_code == 200
    assert decision.json()["summary"]["unresolved"] == 0

    approval = client.post(
        f"/jobs/{job_id}/image-plan/approve",
        json={"allow_paid_api": False, "max_budget_usd": 0},
    )
    assert approval.status_code == 200
    assert client.post(
        f"/jobs/{job_id}/image-plan/approve",
        json={"allow_paid_api": False, "max_budget_usd": 0},
    ).status_code == 409

    job = _wait_state(job_id, ("review",))
    assert job["state"] == "review", job
    assert job["blocks"] > 0
    assert job["progress"]["images"]["completed"] == job["progress"]["images"]["total"]
    assert job["progress"]["images"]["stage"] == "completed"

    ir = client.get(f"/jobs/{job_id}/ir").json()
    first = next(b for b in ir["blocks"] if b["type"] != "image" and b["source_text"])

    # Human-in-the-loop edit.
    pr = client.patch(f"/jobs/{job_id}/blocks/{first['id']}",
                      json={"target_text": "人工修订"})
    assert pr.status_code == 200

    rr = client.post(f"/jobs/{job_id}/render")
    assert rr.status_code == 200 and rr.json()["has_output"]

    dl = client.get(f"/jobs/{job_id}/download")
    assert dl.status_code == 200
    assert dl.content[:2] == b"PK"  # pptx is a zip


def test_missing_job_404():
    assert client.get("/jobs/doesnotexist").status_code == 404


def test_rejects_same_or_unsupported_language(sample_pptx):
    with open(sample_pptx, "rb") as fh:
        same = client.post(
            "/jobs",
            files={"file": ("sample.pptx", fh)},
            data={"source_lang": "de", "target_lang": "de", "images": "false"},
        )
    assert same.status_code == 422
    assert "must be different" in same.json()["detail"]

    with open(sample_pptx, "rb") as fh:
        unsupported = client.post(
            "/jobs",
            files={"file": ("sample.pptx", fh)},
            data={"source_lang": "fr", "target_lang": "de", "images": "false"},
        )
    assert unsupported.status_code == 422
    assert "supported languages" in unsupported.json()["detail"]


def test_rejects_invalid_translation_provider_configuration(sample_pptx, monkeypatch):
    monkeypatch.setattr("translayer.api.app.settings.deepl_api_key", "")
    with open(sample_pptx, "rb") as fh:
        invalid_url = client.post(
            "/jobs",
            files={"file": ("sample.pptx", fh)},
            data={
                "source_lang": "en",
                "target_lang": "de",
                "translation_engine": "openai",
                "translation_api_url": "llm.internal/v1",
                "translation_model": "local-model",
                "images": "false",
            },
        )
    assert invalid_url.status_code == 422
    assert "http:// or https://" in invalid_url.json()["detail"]

    with open(sample_pptx, "rb") as fh:
        missing_deepl_key = client.post(
            "/jobs",
            files={"file": ("sample.pptx", fh)},
            data={
                "source_lang": "en",
                "target_lang": "de",
                "translation_engine": "deepl",
                "images": "false",
            },
        )
    assert missing_deepl_key.status_code == 422
    assert "DeepL API key" in missing_deepl_key.json()["detail"]
