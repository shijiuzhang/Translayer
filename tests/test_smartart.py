"""SmartArt (diagram) text extraction and write-back tests."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from translayer.parsers.pptx_parser import PptxParser
from translayer.renderers.pptx_renderer import PptxRenderer

_NS_DGM = "http://schemas.openxmlformats.org/drawingml/2006/diagram"
_NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _qtag(ns: str, tag: str) -> str:
    return f"{{{ns}}}{tag}"


def _sample_data_xml() -> str:
    return """\
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<dgm:dataModel xmlns:dgm="http://schemas.openxmlformats.org/drawingml/2006/diagram"
               xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <dgm:ptLst>
    <dgm:pt modelId="{A}">
      <dgm:t>
        <a:p><a:r><a:t>Standard Features</a:t></a:r></a:p>
      </dgm:t>
    </dgm:pt>
    <dgm:pt modelId="{B}">
      <dgm:t>
        <a:p><a:r><a:t>Business Use Cases</a:t></a:r></a:p>
        <a:p><a:r><a:t>Second line</a:t></a:r></a:p>
      </dgm:t>
    </dgm:pt>
    <dgm:pt modelId="{C}">
      <dgm:t>
        <a:p><a:endParaRPr lang="en-US"/></a:p>
      </dgm:t>
    </dgm:pt>
  </dgm:ptLst>
</dgm:dataModel>
"""


def test_parser_extracts_point_text() -> None:
    parser = PptxParser()
    root = ET.fromstring(_sample_data_xml())
    pts = root.findall(f".//{_qtag(_NS_DGM, 'pt')}")

    texts = [parser._point_text(pt) for pt in pts]
    assert texts == [
        "Standard Features",
        "Business Use CasesSecond line",
        "",
    ]


def test_renderer_replaces_point_text() -> None:
    renderer = PptxRenderer()
    root = ET.fromstring(_sample_data_xml())
    pts = root.findall(f".//{_qtag(_NS_DGM, 'pt')}")

    renderer._set_point_text(pts[1], "业务用例")

    # Verify the point now contains exactly one paragraph with the new text.
    t_elem = pts[1].find(_qtag(_NS_DGM, "t"))
    assert t_elem is not None
    paragraphs = t_elem.findall(_qtag(_NS_A, "p"))
    assert len(paragraphs) == 1
    run_text = paragraphs[0].find(f".//{_qtag(_NS_A, 't')}")
    assert run_text is not None
    assert run_text.text == "业务用例"

    # Original multi-paragraph text should be gone.
    all_text = "".join(t.text or "" for t in t_elem.findall(f".//{_qtag(_NS_A, 't')}"))
    assert all_text == "业务用例"
