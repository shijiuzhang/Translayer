"""Translayer command-line interface."""

from __future__ import annotations

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
):
    """Translate a document end-to-end."""
    from translayer.pipeline import translate_document

    translate_document(
        input_path, output,
        source_lang=from_lang, target_lang=to_lang,
        translation_engine=engine, ocr_engine=ocr_engine,
        inpaint_engine=inpaint_engine, glossary=glossary,
        images=not no_images,
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
):
    """Translate text embedded in one image while preserving its visual design."""
    from translayer.plugins import registry

    registry.discover()
    localizer = registry.get("image_localization", engine)
    localizer.localize(input_path, output, src=from_lang, tgt=to_lang)
    typer.echo(f"Wrote {output}")


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000):
    """Start the review web UI + API."""
    import uvicorn

    uvicorn.run("translayer.api.app:app", host=host, port=port)


if __name__ == "__main__":
    app()
