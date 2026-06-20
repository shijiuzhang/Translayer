from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from translayer.ir.models import ImageTextRegion, Position
from translayer.plugins import registry


def test_pillow_engine_erases_solid_region() -> None:
    background = (173, 216, 230)
    artifact_dir = Path(__file__).parent / ".inpaint_artifacts"
    image_path = artifact_dir / "source.png"
    out_path = artifact_dir / "erased.png"
    bbox = Position(x=12, y=10, w=28, h=14)

    artifact_dir.mkdir(exist_ok=True)
    try:
        image = Image.new("RGB", (64, 40), background)
        draw = ImageDraw.Draw(image)
        draw.rectangle((bbox.x, bbox.y, bbox.x + bbox.w - 1, bbox.y + bbox.h - 1), fill=(0, 0, 0))
        image.save(image_path)

        registry.discover()
        engine = registry.get("inpaint", "pillow")
        assert engine.erase(str(image_path), [_region(bbox)], str(out_path)) == str(out_path)

        erased = Image.open(out_path).convert("RGB")
        pixels = [
            erased.getpixel((x, y))
            for y in range(bbox.y, bbox.y + bbox.h)
            for x in range(bbox.x, bbox.x + bbox.w)
        ]
        avg = tuple(sum(pixel[channel] for pixel in pixels) / len(pixels) for channel in range(3))

        assert all(abs(avg[channel] - background[channel]) < 3 for channel in range(3))
        assert all(sum(pixel) > 30 for pixel in pixels)
    finally:
        image_path.unlink(missing_ok=True)
        out_path.unlink(missing_ok=True)
        artifact_dir.rmdir()


def test_inpaint_engines_are_registered() -> None:
    registry.discover()

    available = registry.available("inpaint")

    assert "pillow" in available
    assert "opencv" in available
    assert "lama" in available


def _region(bbox: Position) -> ImageTextRegion:
    return ImageTextRegion(id="r1", bbox=bbox, source_text="text", background_kind="solid")
