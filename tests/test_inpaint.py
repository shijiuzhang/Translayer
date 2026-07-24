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


def test_pillow_engine_uses_line_erase_boxes_instead_of_paragraph_bbox(
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "source.png"
    out_path = tmp_path / "erased.png"
    image = Image.new("RGB", (100, 70), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 10, 89, 59), fill=(220, 220, 220))
    draw.rectangle((15, 15, 84, 24), fill=(0, 0, 0))
    draw.rectangle((15, 45, 84, 54), fill=(0, 0, 0))
    image.save(image_path)
    region = ImageTextRegion(
        id="r1",
        bbox=Position(x=10, y=10, w=80, h=50),
        erase_boxes=[
            Position(x=15, y=15, w=70, h=10),
            Position(x=15, y=45, w=70, h=10),
        ],
        source_text="two lines",
        background_kind="solid",
    )

    registry.discover()
    registry.get("inpaint", "pillow").erase(
        str(image_path), [region], str(out_path)
    )

    erased = Image.open(out_path).convert("RGB")
    assert erased.getpixel((50, 20)) != (0, 0, 0)
    assert erased.getpixel((50, 50)) != (0, 0, 0)
    assert erased.getpixel((50, 35)) == (220, 220, 220)


def _region(bbox: Position) -> ImageTextRegion:
    return ImageTextRegion(id="r1", bbox=bbox, source_text="text", background_kind="solid")
