"""Run a focused Gemini image-localization experiment on selected PPTX slides.

The script extracts the largest raster image from each selected slide and asks
Gemini to produce one localized image per target language. It intentionally does
not rewrite the PPTX yet: the purpose of this experiment is to compare image
quality before integrating the provider into the end-to-end pipeline.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from translayer.pipeline import parse_document
from translayer.plugins import registry

_SLIDE_ID_RE = re.compile(r"^s(?P<index>\d+)-")


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _slide_index(image_id: str) -> int | None:
    match = _SLIDE_ID_RE.match(image_id)
    return int(match.group("index")) if match else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pptx", type=Path)
    parser.add_argument("--slides", default="16,17,18", help="1-based slide numbers")
    parser.add_argument("--targets", default="zh,de", help="comma-separated target languages")
    parser.add_argument("--output-dir", type=Path, default=Path("gemini-validation"))
    parser.add_argument("--dry-run", action="store_true", help="extract and select without API calls")
    args = parser.parse_args()

    slides = {int(value) - 1 for value in _csv(args.slides)}
    targets = _csv(args.targets)
    if not slides or not targets:
        raise SystemExit("At least one slide and target language are required")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    asset_dir = args.output_dir / "source-assets"
    ir = parse_document(
        str(args.pptx),
        source_lang="en",
        target_lang=targets[0],
        asset_dir=str(asset_dir),
    )

    selected = []
    for slide_index in sorted(slides):
        candidates = [
            image for image in ir.resources.images if _slide_index(image.id) == slide_index
        ]
        if not candidates:
            print(f"Slide {slide_index + 1}: no raster image found; skipped")
            continue
        image = max(candidates, key=lambda item: item.width * item.height)
        selected.append((slide_index + 1, image))
        print(f"Slide {slide_index + 1}: selected {image.id} ({image.width}x{image.height})")

    if args.dry_run:
        return

    registry.discover()
    engine = registry.get("image_localization", "gemini")
    for target in targets:
        target_dir = args.output_dir / target
        target_dir.mkdir(parents=True, exist_ok=True)
        for slide_number, image in selected:
            suffix = Path(image.data_ref).suffix or ".png"
            output = target_dir / f"slide-{slide_number}-{image.id}{suffix}"
            engine.localize(image.data_ref, str(output), src="en", tgt=target)
            print(f"Wrote {output}")


if __name__ == "__main__":
    main()
