"""HTML parser + renderer round-trip tests."""

from __future__ import annotations

from translayer.parsers.html_parser import HtmlParser
from translayer.renderers.html_renderer import HtmlRenderer

_SAMPLE_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head><title>Quarterly Report</title></head>
<body>
  <h1>Quarterly Results</h1>
  <p>Revenue grew strongly this quarter.</p>
  <p>Costs were well managed.</p>
  <h2>Key Metrics</h2>
  <table>
    <tr><th>Metric</th><th>Value</th></tr>
    <tr><td>Revenue</td><td>5000</td></tr>
    <tr><td>Users</td><td>1000</td></tr>
  </table>
  <ul>
    <li>First bullet point.</li>
    <li>Second bullet point.</li>
  </ul>
  <img src="chart.png" alt="Revenue chart" />
</body>
</html>
"""


def _make_sample_html(tmp_path) -> str:
    out = str(tmp_path / "sample.html")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(_SAMPLE_HTML)
    return out


def test_parse_extracts_headings_and_paragraphs(tmp_path):
    sample = _make_sample_html(tmp_path)
    ir = HtmlParser().parse(sample, {"source_lang": "en", "target_lang": "zh"})

    texts = [b.source_text for b in ir.blocks if b.type != "image"]
    assert "Quarterly Results" in texts
    assert "Revenue grew strongly this quarter." in texts
    assert "Costs were well managed." in texts

    headings = [b for b in ir.blocks if b.type == "heading"]
    assert len(headings) >= 2


def test_parse_extracts_table_cells(tmp_path):
    sample = _make_sample_html(tmp_path)
    ir = HtmlParser().parse(sample, {"source_lang": "en", "target_lang": "zh"})

    table_blocks = [b for b in ir.blocks if b.type == "table_cell"]
    assert len(table_blocks) >= 4
    texts = {b.source_text for b in table_blocks}
    assert "Metric" in texts
    assert "Revenue" in texts
    assert "5000" in texts


def test_parse_extracts_list_items(tmp_path):
    sample = _make_sample_html(tmp_path)
    ir = HtmlParser().parse(sample, {"source_lang": "en", "target_lang": "zh"})

    list_items = [b for b in ir.blocks if b.type == "list_item"]
    assert len(list_items) == 2
    texts = {b.source_text for b in list_items}
    assert "First bullet point." in texts
    assert "Second bullet point." in texts


def test_parse_extracts_title(tmp_path):
    sample = _make_sample_html(tmp_path)
    ir = HtmlParser().parse(sample, {})

    assert ir.meta.title == "Quarterly Report"


def test_parse_image_alt_text(tmp_path):
    sample = _make_sample_html(tmp_path)
    ir = HtmlParser().parse(sample, {})

    image_blocks = [b for b in ir.blocks if b.type == "image"]
    assert len(image_blocks) == 1
    assert image_blocks[0].source_text == "Revenue chart"
    assert image_blocks[0].translatable is True


def test_render_writes_back_translations(tmp_path):
    sample = _make_sample_html(tmp_path)
    parser, renderer = HtmlParser(), HtmlRenderer()
    ir = parser.parse(sample, {})

    mapping = {
        "Quarterly Results": "季度业绩",
        "Revenue grew strongly this quarter.": "本季度收入大幅增长。",
        "Costs were well managed.": "成本控制良好。",
        "Metric": "指标",
        "Value": "数值",
    }
    for b in ir.blocks:
        if b.source_text in mapping:
            b.target_text = mapping[b.source_text]

    out = str(tmp_path / "out.html")
    renderer.render(ir, sample, out)

    with open(out, encoding="utf-8") as fh:
        html = fh.read()

    assert "季度业绩" in html
    assert "本季度收入大幅增长。" in html
    assert "指标" in html
    assert "Quarterly Results" not in html


def test_render_preserves_structure(tmp_path):
    sample = _make_sample_html(tmp_path)
    parser, renderer = HtmlParser(), HtmlRenderer()
    ir = parser.parse(sample, {})

    out = str(tmp_path / "identity.html")
    renderer.render(ir, sample, out)

    with open(out, encoding="utf-8") as fh:
        html = fh.read()

    assert "<h1" in html
    assert "<h2" in html
    assert "<table" in html
    assert "<ul" in html
    assert "<img" in html


def test_render_image_alt_translation(tmp_path):
    sample = _make_sample_html(tmp_path)
    parser, renderer = HtmlParser(), HtmlRenderer()
    ir = parser.parse(sample, {})

    for b in ir.blocks:
        if b.type == "image" and b.source_text == "Revenue chart":
            b.target_text = "收入图表"

    out = str(tmp_path / "img_alt.html")
    renderer.render(ir, sample, out)

    with open(out, encoding="utf-8") as fh:
        html = fh.read()

    assert 'alt="收入图表"' in html


def test_blocks_have_data_tl_id(tmp_path):
    sample = _make_sample_html(tmp_path)
    ir = HtmlParser().parse(sample, {})

    for b in ir.blocks:
        if b.type != "image":
            assert b.source_ref.kind in ("html_element", "heading", "list_item", "table_cell")
