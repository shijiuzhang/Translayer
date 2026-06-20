"""Parser + renderer round-trip and write-back tests."""

from __future__ import annotations

from pptx import Presentation

from translayer.parsers.pptx_parser import PptxParser
from translayer.renderers.pptx_renderer import PptxRenderer


def test_parse_extracts_blocks_and_images(sample_pptx):
    ir = PptxParser().parse(sample_pptx, {"source_lang": "en", "target_lang": "zh"})
    texts = [b.source_text for b in ir.blocks if b.type != "image"]
    assert "Quarterly Results" in texts
    assert "Revenue grew strongly." in texts
    assert "Costs were controlled." in texts
    # table cells
    assert "Metric" in texts and "Users" in texts and "1000" in texts
    # one image extracted
    assert len(ir.resources.images) == 1
    img = ir.resources.images[0]
    assert img.width == 400 and img.height == 200
    # title role detected
    assert any(b.semantic_role == "title" for b in ir.blocks)


def test_source_refs_are_addressable(sample_pptx):
    ir = PptxParser().parse(sample_pptx, {})
    for b in ir.blocks:
        if b.type == "table_cell":
            assert b.source_ref.row is not None and b.source_ref.col is not None
        elif b.type == "image":
            assert b.source_ref.image_id is not None
        else:
            assert b.source_ref.paragraph_index is not None


def test_render_writes_back_translations(sample_pptx, tmp_path):
    parser, renderer = PptxParser(), PptxRenderer()
    ir = parser.parse(sample_pptx, {})

    mapping = {
        "Quarterly Results": "季度业绩",
        "Revenue grew strongly.": "收入大幅增长。",
        "Costs were controlled.": "成本得到控制。",
        "Metric": "指标",
        "Value": "数值",
        "Users": "用户",
        "1000": "1000",
    }
    for b in ir.blocks:
        if b.source_text in mapping:
            b.target_text = mapping[b.source_text]

    out = str(tmp_path / "out.pptx")
    renderer.render(ir, sample_pptx, out)

    prs = Presentation(out)
    all_text = []
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                all_text.append(shape.text_frame.text)
            if shape.has_table:
                for row in shape.table.rows:
                    for cell in row.cells:
                        all_text.append(cell.text_frame.text)
    blob = "\n".join(all_text)
    assert "季度业绩" in blob
    assert "收入大幅增长。" in blob
    assert "成本得到控制。" in blob
    assert "指标" in blob and "用户" in blob
    # English originals are gone
    assert "Quarterly Results" not in blob
    assert "Revenue grew strongly." not in blob


def test_roundtrip_preserves_structure(sample_pptx, tmp_path):
    parser, renderer = PptxParser(), PptxRenderer()
    ir = parser.parse(sample_pptx, {})
    out = str(tmp_path / "identity.pptx")
    renderer.render(ir, sample_pptx, out)  # no target_text set -> identity-ish
    src, dst = Presentation(sample_pptx), Presentation(out)
    assert len(src.slides) == len(dst.slides)
    for s1, s2 in zip(src.slides, dst.slides, strict=False):
        assert len(s1.shapes) == len(s2.shapes)
