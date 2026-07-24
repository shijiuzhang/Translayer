"""FastAPI application: job API + review UI.

Pipeline up to ``review`` runs in a background thread so the upload returns
immediately. Editing block/region translations is the human-in-the-loop step;
``/render`` then produces the final document.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from translayer.api.jobs import Job, JobStore
from translayer.api.schemas import (
    ApproveImagePlan,
    BlockEdit,
    BulkImageDecisionEdit,
    ImageDecisionEdit,
    RegionEdit,
)
from translayer.config import settings
from translayer.engines.image.cost_guard import ImageAPICostGuard
from translayer.enrich.image_text import ImageTextEnricher
from translayer.languages import normalize_language
from translayer.localize.image_pipeline import localize_images
from translayer.localize.text_pipeline import localize_text
from translayer.localize.whole_image_quality import (
    ImageLocalizationQualityError,
    prepare_text_mappings,
    validate_localized_output,
)
from translayer.pipeline import enrich_document, parse_document, render_document
from translayer.plugins import registry

app = FastAPI(title="Translayer", version="0.2.3")
store = JobStore()

def _web_dir() -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return Path(bundle_root) / "translayer" / "web"
    return Path(__file__).resolve().parents[1] / "web"


_WEB_DIR = _web_dir()


def _process(job: Job) -> None:
    try:
        job.state = "parsing"
        ir = parse_document(
            job.input_path, job.source_lang, job.target_lang,
            asset_dir=os.path.join(job.work_dir, "assets"),
        )
        job.ir = ir
        job.state = "screening"
        enrich_document(ir, images=job.images, ocr_engine=job.ocr_engine)
        job.initialize_image_decisions()
        job.state = "localizing_text"
        localize_text(
            ir,
            engine_name=job.translation_engine,
            engine_options=job.translation_options,
            progress_callback=lambda progress: job.update_progress("text", **progress),
        )
        job.state = "image_review" if job.images and ir.resources.images else "review"
    except Exception as exc:  # noqa: BLE001 - surface failures to the client
        job.state = "error"
        job.error = f"{type(exc).__name__}: {exc}"


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    path = _WEB_DIR / "index.html"
    with open(path, encoding="utf-8") as fh:
        return fh.read()


@app.get("/configuration")
def public_configuration():
    """Return non-secret defaults used by the browser's cost preview."""
    return {
        "gemini_image_model": settings.gemini_image_model,
        "gemini_estimated_cost_per_image_usd": settings.gemini_image_estimated_cost_usd,
        "gemini_key_configured_on_server": bool(settings.gemini_api_key),
    }


@app.post("/jobs")
async def create_job(
    file: UploadFile = File(...),
    source_lang: str = Form("en"),
    target_lang: str = Form("zh"),
    translation_engine: str | None = Form(None),
    translation_api_url: str | None = Form(None),
    translation_api_key: str | None = Form(None),
    translation_model: str | None = Form(None),
    gemini_api_key: str | None = Form(None),
    gemini_model: str | None = Form(None),
    ocr_engine: str | None = Form(None),
    inpaint_engine: str | None = Form(None),
    images: bool = Form(True),
):
    try:
        source_lang = normalize_language(source_lang)
        target_lang = normalize_language(target_lang)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if source_lang == target_lang:
        raise HTTPException(422, "source and target languages must be different")
    selected_engine = translation_engine or settings.translation_engine
    if selected_engine not in {"openai", "deepl", "mock"}:
        raise HTTPException(422, "unsupported translation engine")
    translation_options: dict[str, str] = {}
    if selected_engine == "openai":
        if translation_api_url:
            translation_options["base_url"] = translation_api_url
        if translation_api_key is not None:
            translation_options["api_key"] = translation_api_key
        if translation_model:
            translation_options["model"] = translation_model
        if not (translation_model or settings.openai_model):
            raise HTTPException(422, "model name is required for an OpenAI-compatible engine")
    elif selected_engine == "deepl":
        if translation_api_key:
            translation_options["api_key"] = translation_api_key
        if translation_api_url:
            translation_options["base_url"] = translation_api_url
        if not (translation_api_key or settings.deepl_api_key):
            raise HTTPException(422, "DeepL API key is required")
    try:
        registry.discover()
        registry.get("translation", selected_engine, **translation_options)
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc

    data = await file.read()
    job = store.create(
        data, file.filename or "input.pptx", source_lang, target_lang,
        translation_engine=selected_engine,
        translation_options=translation_options,
        gemini_api_key=gemini_api_key,
        gemini_model=gemini_model,
        ocr_engine=ocr_engine,
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


def _slide_number(image_id: str) -> int | None:
    match = re.match(r"^s(\d+)-", image_id)
    return int(match.group(1)) + 1 if match else None


@app.get("/jobs/{job_id}/image-plan")
def get_image_plan(job_id: str):
    job = _require(job_id)
    if job.ir is None:
        raise HTTPException(409, f"image plan not ready (state={job.state})")
    route_counts: dict[str, int] = {}
    action_counts: dict[str, int] = {}
    images = []
    for image in job.ir.resources.images:
        selection = image.selection
        route = selection.route if selection else "review"
        route_counts[route] = route_counts.get(route, 0) + 1
        decision = job.image_decisions.get(image.id)
        action = decision.action if decision else None
        if action:
            action_counts[action] = action_counts.get(action, 0) + 1
        images.append(
            {
                "image_id": image.id,
                "slide_number": _slide_number(image.id),
                "width": image.width,
                "height": image.height,
                "preview_url": f"/jobs/{job.id}/images/{image.id}/preview",
                "slide_preview_url": (
                    f"/jobs/{job.id}/slides/{_slide_number(image.id)}/preview"
                    if _slide_number(image.id)
                    else None
                ),
                "selection": selection.model_dump(mode="json") if selection else None,
                "decision": decision.public() if decision else None,
                "localization_validation": image.localization_validation.model_dump(mode="json"),
                "localized_preview_url": (
                    f"/jobs/{job.id}/images/{image.id}/localized-preview"
                    if image.localized_data_ref or image.rejected_data_ref
                    else None
                ),
            }
        )
    return {
        "job_id": job.id,
        "state": job.state,
        "target_lang": job.target_lang,
        "plan_locked": job.image_plan_locked,
        "summary": {
            "total_images": len(images),
            "routes": route_counts,
            "actions": action_counts,
            "unresolved": job.unresolved_images(),
            "planned_paid_calls": job.planned_paid_calls(),
            "estimated_cost_per_call_usd": job.estimated_image_cost_usd,
            "estimated_total_cost_usd": job.estimated_image_spend(),
            "budget_usd": job.image_budget_usd,
        },
        "images": images,
    }


@app.get("/jobs/{job_id}/images/{image_id}/preview")
def image_preview(job_id: str, image_id: str):
    job = _require(job_id)
    if job.ir is None:
        raise HTTPException(409, "images not ready")
    image = job.ir.image_by_id(image_id)
    if image is None or not os.path.exists(image.data_ref):
        raise HTTPException(404, "image not found")
    return FileResponse(image.data_ref, media_type=image.media_type)


@app.get("/jobs/{job_id}/images/{image_id}/localized-preview")
def localized_image_preview(job_id: str, image_id: str):
    job = _require(job_id)
    if job.ir is None:
        raise HTTPException(409, "images not ready")
    image = job.ir.image_by_id(image_id)
    if image is None:
        raise HTTPException(404, "image not found")
    path = image.rejected_data_ref or image.localized_data_ref
    if not path or not os.path.exists(path):
        raise HTTPException(404, "localized image not found")
    return FileResponse(path, media_type=image.media_type)


def _ensure_slide_preview(job: Job, slide_number: int) -> str:
    preview_dir = os.path.join(job.work_dir, "slide-previews")
    os.makedirs(preview_dir, exist_ok=True)
    preview_path = os.path.join(preview_dir, f"slide-{slide_number}.png")
    if os.path.exists(preview_path):
        return preview_path
    office = shutil.which("soffice") or shutil.which("libreoffice")
    pdftoppm = shutil.which("pdftoppm")
    if not office or not pdftoppm:
        raise HTTPException(503, "slide preview renderer unavailable")
    with job.slide_preview_lock:
        if os.path.exists(preview_path):
            return preview_path
        pdfs = [name for name in os.listdir(preview_dir) if name.endswith(".pdf")]
        if not pdfs:
            office_profile = os.path.join(job.work_dir, "libreoffice-profile")
            os.makedirs(office_profile, exist_ok=True)
            completed = subprocess.run(
                [
                    office,
                    f"-env:UserInstallation=file://{office_profile}",
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    preview_dir,
                    job.input_path,
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=90,
            )
            if completed.returncode != 0:
                raise HTTPException(500, "could not render slide previews")
            pdfs = [name for name in os.listdir(preview_dir) if name.endswith(".pdf")]
        if not pdfs:
            raise HTTPException(500, "slide preview PDF was not created")
        completed = subprocess.run(
            [
                pdftoppm,
                "-png",
                "-r",
                "96",
                "-f",
                str(slide_number),
                "-l",
                str(slide_number),
                "-singlefile",
                os.path.join(preview_dir, pdfs[0]),
                os.path.splitext(preview_path)[0],
            ],
            check=False,
            capture_output=True,
            timeout=30,
        )
        if completed.returncode != 0 or not os.path.exists(preview_path):
            raise HTTPException(404, "slide preview not found")
    return preview_path


@app.get("/jobs/{job_id}/slides/{slide_number}/preview")
def slide_preview(job_id: str, slide_number: int):
    job = _require(job_id)
    if slide_number < 1:
        raise HTTPException(404, "slide preview not found")
    path = _ensure_slide_preview(job, slide_number)
    return FileResponse(path, media_type="image/png")


def _set_image_decision(job: Job, image_id: str, action: str) -> None:
    if job.state != "image_review":
        raise HTTPException(409, f"job is not awaiting image review (state={job.state})")
    if job.image_plan_locked:
        raise HTTPException(409, "image plan is already locked")
    decision = job.image_decisions.get(image_id)
    if decision is None:
        raise HTTPException(404, f"image not found: {image_id}")
    image = job.ir.image_by_id(image_id) if job.ir else None
    if action == "reuse" and (
        image is None or image.selection is None or not image.selection.duplicate_of
    ):
        raise HTTPException(422, "reuse is only available for a detected duplicate image")
    decision.action = action
    decision.source = "user"


@app.patch("/jobs/{job_id}/images/{image_id}/decision")
def edit_image_decision(job_id: str, image_id: str, edit: ImageDecisionEdit):
    job = _require(job_id)
    _set_image_decision(job, image_id, edit.action)
    return get_image_plan(job_id)


@app.post("/jobs/{job_id}/images/decisions/bulk")
def bulk_image_decisions(job_id: str, edit: BulkImageDecisionEdit):
    job = _require(job_id)
    for image_id in edit.image_ids:
        _set_image_decision(job, image_id, edit.action)
    return get_image_plan(job_id)


def _continue_after_image_review(
    job: Job, allow_paid_api: bool, max_budget_usd: float
) -> None:
    try:
        if job.ir is None:
            raise RuntimeError("IR not ready")
        job.state = "localizing_images"
        ir = job.ir
        total_images = len(ir.resources.images)
        completed_image_ids: set[str] = set()

        def update_image_progress(
            stage: str,
            image_id: str | None = None,
            *,
            completed: bool = False,
        ) -> None:
            if completed and image_id:
                completed_image_ids.add(image_id)
            job.update_progress(
                "images",
                completed=len(completed_image_ids),
                total=total_images,
                current=image_id,
                stage=stage,
            )

        update_image_progress("preparing")
        for image in ir.resources.images:
            decision = job.image_decisions[image.id]
            if decision.action in {"preserve", "logo", "reuse"}:
                image.text_regions = []
                if decision.action in {"preserve", "logo"}:
                    update_image_progress(
                        "preserved",
                        image.id,
                        completed=True,
                    )
            elif decision.action == "region" and image.selection:
                image.selection.route = "region"

        image_text_enricher = ImageTextEnricher(
            job.ocr_engine,
            source_lang=job.source_lang,
        )
        region_images = [
            image
            for image in ir.resources.images
            if job.image_decisions[image.id].action == "region"
        ]
        for image in region_images:
            update_image_progress("ocr", image.id)
            image_text_enricher.detect_image(image)

        paid_images = [
            image
            for image in ir.resources.images
            if job.image_decisions[image.id].action == "whole_image"
            and image.localization_validation.status != "passed"
        ]
        if paid_images:
            guard = ImageAPICostGuard(
                enabled=allow_paid_api,
                max_calls=len(paid_images),
                max_cost_usd=max_budget_usd,
                estimated_cost_per_call_usd=job.estimated_image_cost_usd,
            )
            registry.discover()
            engine = registry.get(
                "image_localization",
                "gemini",
                cost_guard=guard,
                api_key=job.gemini_api_key or None,
                model=job.gemini_model,
            )
            output_dir = os.path.join(job.work_dir, "localized-images", job.target_lang)
            os.makedirs(output_dir, exist_ok=True)
            quality_failures = []
            for image in paid_images:
                extension = os.path.splitext(image.data_ref)[1] or ".png"
                output = os.path.join(output_dir, f"{image.id}{extension}")
                try:
                    try:
                        update_image_progress("ocr", image.id)
                        ImageTextEnricher(
                            job.ocr_engine,
                            source_lang=job.source_lang,
                        ).detect_image(image, bypass_route=True, strict=True)
                    except Exception as exc:  # noqa: BLE001 - fail closed before paid generation
                        image.localization_validation.status = "failed"
                        image.localization_validation.reason = (
                            f"pre_generation_ocr_failed:{type(exc).__name__}"
                        )
                        quality_failures.append(image)
                        continue
                    update_image_progress("translating", image.id)
                    mappings = prepare_text_mappings(
                        image,
                        translation_engine=job.translation_engine,
                        source_lang=job.source_lang,
                        target_lang=job.target_lang,
                        translation_options=job.translation_options,
                    )
                    update_image_progress("generating", image.id)
                    engine.localize(
                        image.data_ref,
                        output,
                        src=job.source_lang,
                        tgt=job.target_lang,
                        text_mappings=mappings,
                    )
                    update_image_progress("validating", image.id)
                    validation = validate_localized_output(
                        image,
                        output,
                        ocr_engine=job.ocr_engine,
                        source_lang=job.source_lang,
                        target_lang=job.target_lang,
                    )
                    if validation.status != "passed":
                        engine.invalidate_cache(
                            image.data_ref,
                            job.source_lang,
                            job.target_lang,
                            mappings,
                        )
                        image.rejected_data_ref = output
                        image.localized_data_ref = None
                        quality_failures.append(image)
                    else:
                        image.localized_data_ref = output
                        image.rejected_data_ref = None
                except ImageLocalizationQualityError:
                    quality_failures.append(image)
                except Exception as exc:  # noqa: BLE001 - return the image to review
                    image.localization_validation.status = "failed"
                    image.localization_validation.reason = (
                        f"image_generation_failed:{type(exc).__name__}"
                    )
                    quality_failures.append(image)
                finally:
                    stage = (
                        "completed"
                        if image.localization_validation.status == "passed"
                        else "failed"
                    )
                    update_image_progress(stage, image.id, completed=True)
            job.paid_image_calls += guard.calls_reserved
            if quality_failures:
                for image in quality_failures:
                    decision = job.image_decisions[image.id]
                    decision.action = None
                    decision.source = "quality_check"
                job.image_plan_locked = False
                job.image_budget_usd = 0.0
                job.state = "image_review"
                return

        localize_images(
            ir,
            translation_engine=job.translation_engine,
            inpaint_engine=job.inpaint_engine,
            translation_options=job.translation_options,
            progress_callback=lambda stage, image: update_image_progress(
                stage,
                image.id,
                completed=stage == "completed",
            ),
        )
        for image in region_images:
            if image.id not in completed_image_ids:
                update_image_progress("completed", image.id, completed=True)
        for image in ir.resources.images:
            decision = job.image_decisions[image.id]
            if decision.action != "reuse" or not image.selection or not image.selection.duplicate_of:
                continue
            update_image_progress("reusing", image.id)
            source = ir.image_by_id(image.selection.duplicate_of)
            image.localized_data_ref = source.localized_data_ref if source else None
            update_image_progress("completed", image.id, completed=True)
        for image in ir.resources.images:
            if image.id not in completed_image_ids:
                update_image_progress("completed", image.id, completed=True)
        update_image_progress("completed")
        job.state = "review"
    except Exception as exc:  # noqa: BLE001
        job.state = "error"
        job.error = f"{type(exc).__name__}: {exc}"


@app.post("/jobs/{job_id}/image-plan/approve")
def approve_image_plan(job_id: str, approval: ApproveImagePlan):
    job = _require(job_id)
    if job.state != "image_review":
        raise HTTPException(409, f"job is not awaiting image review (state={job.state})")
    if job.unresolved_images():
        raise HTTPException(409, f"{job.unresolved_images()} image decisions remain unresolved")
    estimated = job.estimated_image_spend()
    if estimated > approval.max_budget_usd + 1e-9:
        raise HTTPException(
            409,
            f"estimated image cost ${estimated:.2f} exceeds budget ${approval.max_budget_usd:.2f}",
        )
    if job.planned_paid_calls() and not approval.allow_paid_api:
        raise HTTPException(409, "paid image calls are not explicitly enabled")
    if approval.gemini_api_key is not None:
        job.gemini_api_key = approval.gemini_api_key.strip()
    if approval.gemini_model:
        job.gemini_model = approval.gemini_model.strip()
    if job.planned_paid_calls() and not (job.gemini_api_key or settings.gemini_api_key):
        raise HTTPException(
            409,
            "Gemini API key is required only because the plan modifies text inside images",
        )
    job.image_plan_locked = True
    job.image_budget_usd = approval.max_budget_usd
    job.state = "localizing_images"
    threading.Thread(
        target=_continue_after_image_review,
        args=(job, approval.allow_paid_api, approval.max_budget_usd),
        daemon=True,
    ).start()
    return job.public()


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
    if job.state not in {"review", "done"}:
        raise HTTPException(409, f"job is not ready to render (state={job.state})")
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
    filename = f"translayer-{job.source_lang}-to-{job.target_lang}{ext or '.pptx'}"
    return FileResponse(job.output_path, media_type=media_type, filename=filename)
