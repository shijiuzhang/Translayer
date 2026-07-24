from translayer.ir.models import ImageTextRegion, Position
from translayer.localize.image_pipeline import _use_text_canvas


def _region(text: str) -> ImageTextRegion:
    return ImageTextRegion(
        id="r1",
        bbox=Position(x=0, y=0, w=100, h=30),
        source_text=text,
    )


def test_dense_local_ocr_content_uses_clean_text_canvas() -> None:
    assert _use_text_canvas([_region("纯文本截图" * 10)])


def test_short_label_keeps_region_overlay() -> None:
    assert not _use_text_canvas([_region("短标签")])
