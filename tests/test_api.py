"""API tests via FastAPI TestClient using offline mock engines."""

from __future__ import annotations

import io
import time

from fastapi.testclient import TestClient

from translayer.api.app import app

client = TestClient(app)


def _wait_review(job_id: str, timeout: float = 10.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/jobs/{job_id}").json()
        if job["state"] in ("review", "done", "error"):
            return job
        time.sleep(0.1)
    raise AssertionError("job did not reach review")


def test_index_served():
    r = client.get("/")
    assert r.status_code == 200
    assert "Translayer" in r.text


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

    job = _wait_review(job_id)
    assert job["state"] == "review", job
    assert job["blocks"] > 0

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
