"""Translayer command-line interface."""

from __future__ import annotations

import json
from pathlib import Path

import typer

app = typer.Typer(help="Translayer — translate documents without breaking layout.")


@app.command()
def translate(
    input_path: str = typer.Argument(..., help="Input document (e.g. deck.pptx)"),
    output: str = typer.Option(..., "--output", "-o", help="Output path"),
    from_lang: str = typer.Option("en", "--from", help="Source language"),
    to_lang: str = typer.Option("zh", "--to", help="Target language"),
    engine: str | None = typer.Option(None, "--engine", help="Translation engine key"),
    ocr_engine: str | None = typer.Option(None, "--ocr-engine", help="OCR engine key (tesseract, cloud_vision, paddle, mock)"),
    inpaint_engine: str | None = typer.Option(None, "--inpaint-engine", help="Inpaint engine key (pillow, opencv, lama)"),
    glossary: str | None = typer.Option(None, "--glossary", help="CSV glossary (source,target)"),
    no_images: bool = typer.Option(False, "--no-images", help="Skip in-image text translation"),
    no_image_screening: bool = typer.Option(
        False,
        "--no-image-screening",
        help="Disable safe local image routing (not recommended)",
    ),
):
    """Translate a document end-to-end."""
    from translayer.pipeline import translate_document

    translate_document(
        input_path, output,
        source_lang=from_lang, target_lang=to_lang,
        translation_engine=engine, ocr_engine=ocr_engine,
        inpaint_engine=inpaint_engine, glossary=glossary,
        images=not no_images, screen_images=not no_image_screening,
    )
    typer.echo(f"Wrote {output}")


@app.command()
def schema(output: str | None = typer.Option(None, "-o", help="Write schema to file")):
    """Print (or write) the DocumentIR JSON Schema."""
    from translayer.ir.schema import dump_schema

    text = dump_schema()
    if output:
        with open(output, "w", encoding="utf-8") as fh:
            fh.write(text)
        typer.echo(f"Wrote {output}")
    else:
        typer.echo(text)


@app.command()
def plugins():
    """List registered plugins."""
    from translayer.plugins import registry

    registry.discover()
    for kind in [
        "parser", "renderer", "translation", "ocr", "inpaint", "image_localization"
    ]:
        typer.echo(f"{kind:12} {registry.available(kind)}")


@app.command("translate-image")
def translate_image(
    input_path: str = typer.Argument(..., help="Input raster image"),
    output: str = typer.Option(..., "--output", "-o", help="Output image path"),
    from_lang: str = typer.Option("en", "--from", help="Source language"),
    to_lang: str = typer.Option(..., "--to", help="Target language (for example zh or de)"),
    engine: str = typer.Option(
        "gemini", "--engine", help="Whole-image localization engine key"
    ),
    translation_engine: str | None = typer.Option(
        None, "--translation-engine", help="Engine used to build the explicit text map"
    ),
    ocr_engine: str = typer.Option(
        "tesseract", "--ocr-engine", help="OCR engine used before and after generation"
    ),
    allow_paid_api: bool = typer.Option(
        False,
        "--allow-paid-api",
        help="Explicitly permit one bounded paid provider call",
    ),
    max_cost_usd: float = typer.Option(
        0.10, "--max-cost-usd", min=0.01, help="Hard estimated cost ceiling"
    ),
):
    """Translate text embedded in one image while preserving its visual design."""
    from PIL import Image

    from translayer.config import settings
    from translayer.engines.image.cost_guard import ImageAPICostGuard
    from translayer.enrich.image_text import ImageTextEnricher
    from translayer.ir.models import ImageResource
    from translayer.localize.whole_image_quality import (
        prepare_text_mappings,
        validate_localized_output,
    )
    from translayer.plugins import registry

    registry.discover()
    with Image.open(input_path) as source_image:
        width, height = source_image.size
        media_type = Image.MIME.get(source_image.format or "", "image/png")
    image = ImageResource(
        id="cli-image",
        media_type=media_type,
        data_ref=input_path,
        width=width,
        height=height,
    )
    ImageTextEnricher(ocr_engine, source_lang=from_lang).detect_image(
        image,
        bypass_route=True,
        strict=True,
    )
    mappings = prepare_text_mappings(
        image,
        translation_engine=translation_engine or settings.translation_engine,
        source_lang=from_lang,
        target_lang=to_lang,
    )
    guard = ImageAPICostGuard(
        enabled=allow_paid_api,
        max_calls=1,
        max_cost_usd=max_cost_usd,
    )
    localizer = registry.get("image_localization", engine, cost_guard=guard)
    localizer.localize(
        input_path,
        output,
        src=from_lang,
        tgt=to_lang,
        text_mappings=mappings,
    )
    validation = validate_localized_output(
        image,
        output,
        ocr_engine=ocr_engine,
        source_lang=from_lang,
        target_lang=to_lang,
    )
    if validation.status != "passed":
        localizer.invalidate_cache(input_path, from_lang, to_lang, mappings)
        typer.echo(
            f"Rejected {output}: {validation.reason}; "
            f"residual={validation.residual_source_texts}; "
            f"missing={validation.missing_target_texts}",
            err=True,
        )
        raise typer.Exit(code=2)
    typer.echo(f"Wrote verified image {output}")


@app.command("plan-images")
def plan_images(
    input_path: str = typer.Argument(..., help="Input PPTX to inspect locally"),
    output: str = typer.Option(..., "--output", "-o", help="Write JSON plan here"),
    from_lang: str = typer.Option("en", "--from", help="Source language"),
    targets: str = typer.Option("zh,de", "--targets", help="Comma-separated targets"),
    budget_usd: float | None = typer.Option(
        None, "--budget-usd", min=0.0, help="Optional planning budget"
    ),
    estimated_cost_usd: float = typer.Option(
        0.08,
        "--estimated-cost-usd",
        min=0.0,
        help="Conservative estimated cost per whole-image call",
    ),
    tesseract_lang: str = typer.Option(
        "eng", "--tesseract-lang", help="Installed local Tesseract language"
    ),
):
    """Build a zero-API image routing and cost plan."""
    from translayer.enrich.image_selection import (
        ImageSelector,
        TesseractTextProbe,
        plan_payload,
    )
    from translayer.pipeline import parse_document

    target_list = [item.strip() for item in targets.split(",") if item.strip()]
    if not target_list:
        raise typer.BadParameter("At least one target language is required")

    output_path = Path(output)
    asset_dir = output_path.parent / f"{output_path.stem}-assets"
    cache_dir = output_path.parent / ".image-selection-cache"
    ir = parse_document(
        input_path,
        source_lang=from_lang,
        target_lang=target_list[0],
        asset_dir=str(asset_dir),
    )
    selector = ImageSelector(
        probe=TesseractTextProbe(lang=tesseract_lang), cache_dir=cache_dir
    )
    selector.analyze(ir)
    payload = plan_payload(
        ir,
        targets=target_list,
        estimated_cost_per_image=estimated_cost_usd,
        budget_usd=budget_usd,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    summary = payload["summary"]
    typer.echo(
        f"Analyzed {summary['total_images']} images locally; provider calls made: 0"
    )
    typer.echo(f"Routes: {summary['routes']}")
    typer.echo(
        f"Projected paid calls: {summary['projected_paid_calls']} "
        f"(estimated ${summary['estimated_total_cost_usd']:.2f})"
    )
    if not summary["within_budget"]:
        typer.echo("BLOCKED: projected cost exceeds the requested budget")
    typer.echo(f"Wrote {output_path}")


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000):
    """Start the review web UI + API."""
    import uvicorn

    uvicorn.run("translayer.api.app:app", host=host, port=port)


if __name__ == "__main__":
    app()
