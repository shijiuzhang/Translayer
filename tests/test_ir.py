from translayer.ir import (
    Block,
    DocMeta,
    DocumentIR,
    ImageResource,
    ImageTextRegion,
    Position,
    Run,
    SourceRef,
)
from translayer.ir.models import SCHEMA_VERSION
from translayer.ir.schema import ir_json_schema


def _sample_ir() -> DocumentIR:
    return DocumentIR(
        meta=DocMeta(source_lang="en", target_lang="zh", title="Deck"),
        blocks=[
            Block(
                id="s0-sh1-p0-r0",
                type="title",
                semantic_role="title",
                runs=[Run(text="Hello")],
                source_text="Hello",
                source_ref=SourceRef(
                    kind="shape_text", slide_index=0, shape_id=1,
                    paragraph_index=0, run_index=0,
                ),
            ),
            Block(
                id="s0-sh2-p0",
                type="body",
                source_text="Quarterly results",
                source_ref=SourceRef(
                    kind="shape_text", slide_index=0, shape_id=2, paragraph_index=0
                ),
            ),
        ],
    )


def test_schema_version():
    ir = _sample_ir()
    assert ir.schema_version == SCHEMA_VERSION


def test_roundtrip_json():
    ir = _sample_ir()
    data = ir.model_dump_json()
    restored = DocumentIR.model_validate_json(data)
    assert restored == ir


def test_translatable_blocks_and_lookup():
    ir = _sample_ir()
    assert len(ir.translatable_blocks()) == 2
    assert ir.block_by_id("s0-sh1-p0-r0").type == "title"
    assert ir.block_by_id("missing") is None


def test_image_resource_lookup():
    ir = _sample_ir()
    img = ImageResource(
        id="img1",
        media_type="image/png",
        data_ref="/tmp/x.png",
        width=800,
        height=600,
        text_regions=[
            ImageTextRegion(
                id="r1",
                bbox=Position(x=10, y=10, w=100, h=30),
                source_text="Revenue",
            )
        ],
    )
    ir.resources.images.append(img)
    assert ir.image_by_id("img1").text_regions[0].source_text == "Revenue"
    assert ir.image_by_id("nope") is None


def test_json_schema_exports():
    schema = ir_json_schema()
    assert schema["title"] == "DocumentIR"
    assert "blocks" in schema["properties"]
