"""FastAPI application: job API + review UI.

Pipeline up to ``review`` runs in a background thread so the upload returns
immediately. Editing block/region translations is the human-in-the-loop step;
``/render`` then produces the final document.
"""

from __future__ import annotations

import os
import threading

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from translayer.api.jobs import Job, JobStore
from translayer.api.schemas import BlockEdit, RegionEdit
from translayer.localize.orchestrator import localize
from translayer.pipeline import enrich_document, parse_document, render_document

app = FastAPI(title="Translayer", version="0.1.0")
store = JobStore()

_WEB_DIR = os.path.join(os.path.dirname(__file__), "..", "web")


def _process(job: Job) -> None:
    try:
        job.state = "parsing"
        ir = parse_document(
            job.input_path, job.source_lang, job.target_lang,
            asset_dir=os.path.join(job.work_dir, "assets"),
        )
        job.ir = ir
        job.state = "enriching"
        enrich_document(ir, images=job.images, ocr_engine=job.ocr_engine)
        job.state = "localizing"
        localize(
            ir,
            translation_engine=job.translation_engine,
            inpaint_engine=job.inpaint_engine,
            images=job.images,
        )
        job.state = "review"
    except Exception as exc:  # noqa: BLE001 - surface failures to the client
        job.state = "error"
        job.error = f"{type(exc).__name__}: {exc}"


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    path = os.path.join(_WEB_DIR, "index.html")
    with open(path, encoding="utf-8") as fh:
        return fh.read()


@app.post("/jobs")
async def create_job(
    file: UploadFile = File(...),
    source_lang: str = Form("en"),
    target_lang: str = Form("zh"),
    translation_engine: str | None = Form(None),
    ocr_engine: str | None = Form(None),
    inpaint_engine: str | None = Form(None),
    images: bool = Form(True),
):
    data = await file.read()
    job = store.create(
        data, file.filename or "input.pptx", source_lang, target_lang,
        translation_engine=translation_engine, ocr_engine=ocr_engine,
        inpaint_engine=inpaint_engine, images=images,
    )
    threading.Thread(target=_process, args=(job,), daemon=True).start()
    return JSONResponse(job.public(), status_code=201)


def _require(job_id: str) -> Job:
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return job


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    return _require(job_id).public()


@app.get("/jobs/{job_id}/ir")
def get_ir(job_id: str):
    job = _require(job_id)
    if job.ir is None:
        raise HTTPException(409, f"IR not ready (state={job.state})")
    return JSONResponse(job.ir.model_dump(mode="json"))


@app.patch("/jobs/{job_id}/blocks/{block_id}")
def edit_block(job_id: str, block_id: str, edit: BlockEdit):
    job = _require(job_id)
    if job.ir is None:
        raise HTTPException(409, "IR not ready")
    block = job.ir.block_by_id(block_id)
    if block is None:
        raise HTTPException(404, "block not found")
    block.target_text = edit.target_text
    return {"ok": True, "block_id": block_id, "target_text": edit.target_text}


@app.patch("/jobs/{job_id}/images/{image_id}/regions/{region_id}")
def edit_region(job_id: str, image_id: str, region_id: str, edit: RegionEdit):
    job = _require(job_id)
    if job.ir is None:
        raise HTTPException(409, "IR not ready")
    image = job.ir.image_by_id(image_id)
    if image is None:
        raise HTTPException(404, "image not found")
    region = next((r for r in image.text_regions if r.id == region_id), None)
    if region is None:
        raise HTTPException(404, "region not found")
    region.target_text = edit.target_text
    return {"ok": True, "region_id": region_id, "target_text": edit.target_text}


@app.post("/jobs/{job_id}/render")
def render(job_id: str):
    job = _require(job_id)
    if job.ir is None:
        raise HTTPException(409, "IR not ready")
    job.state = "rendering"
    out = os.path.join(job.work_dir, "output.pptx")
    try:
        render_document(job.ir, job.input_path, out)
    except Exception as exc:  # noqa: BLE001
        job.state = "error"
        job.error = str(exc)
        raise HTTPException(500, job.error) from exc
    job.output_path = out
    job.state = "done"
    return job.public()


@app.get("/jobs/{job_id}/download")
def download(job_id: str):
    job = _require(job_id)
    if not job.output_path or not os.path.exists(job.output_path):
        raise HTTPException(409, "no output; call /render first")
    ext = os.path.splitext(job.output_path)[1].lower()
    media_types = {
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".html": "text/html",
        ".htm": "text/html",
    }
    media_type = media_types.get(ext, "application/octet-stream")
    filename = f"translayer-output{ext or '.pptx'}"
    return FileResponse(job.output_path, media_type=media_type, filename=filename)
