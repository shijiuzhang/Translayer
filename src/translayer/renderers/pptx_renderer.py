"""PPTX renderer — lossless write-back of translations into the original file.

The renderer reopens the *original* pptx (guaranteeing nothing else is lost),
locates each shape/paragraph/cell via the block's SourceRef, and replaces the
text while preserving the first run's formatting. Localized images are swapped
in by replacing the underlying image part's blob.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.enum.text import MSO_AUTO_SIZE

from translayer.ir.models import Block, DocumentIR
from translayer.plugins import registry

# --------------------------------------------------------------------------- #
# XML namespaces
# --------------------------------------------------------------------------- #
_NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_NS_DGM = "http://schemas.openxmlformats.org/drawingml/2006/diagram"
_NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"


def _qtag(ns: str, tag: str) -> str:
    return f"{{{ns}}}{tag}"


class PptxRenderer:
    name = "pptx"

    def supported_formats(self) -> list[str]:
        return ["pptx"]

    def render(self, ir: DocumentIR, input_path: str, output_path: str) -> None:
        prs = Presentation(input_path)

        # Index shapes by (slide_index, shape_id) including nested groups.
        shape_index: dict[tuple[int, int], object] = {}
        for s_idx, slide in enumerate(prs.slides):
            for shape in slide.shapes:
                self._index_shape(shape, s_idx, shape_index)

        images = {im.id: im for im in ir.resources.images}
        # Cache loaded SmartArt data parts and their XML roots so multiple
        # points on the same diagram share one in-memory tree and one write-back.
        smartart_cache: dict[object, ET.Element] = {}

        for block in ir.blocks:
            if block.type == "image":
                self._render_image(block, shape_index, images)
                continue
            if block.type == "smartart":
                self._render_smartart(block, shape_index, smartart_cache)
                continue
            if block.target_text is None:
                continue
            self._render_text_block(block, shape_index)

        # Persist any modified SmartArt data parts.
        self._persist_smartart(smartart_cache)

        prs.save(output_path)

    # ------------------------------------------------------------------ #
    def _index_shape(self, shape, slide_index, index) -> None:
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            for sub in shape.shapes:
                self._index_shape(sub, slide_index, index)
            return
        index[(slide_index, int(shape.shape_id))] = shape

    def _render_text_block(self, block: Block, index) -> None:
        ref = block.source_ref
        shape = index.get((ref.slide_index, ref.shape_id))
        if shape is None:
            return

        if ref.kind == "table_cell":
            if not shape.has_table:
                return
            try:
                cell = shape.table.rows[ref.row].cells[ref.col]
            except (IndexError, AttributeError):
                return
            tf = cell.text_frame
        else:
            if not shape.has_text_frame:
                return
            tf = shape.text_frame

        try:
            para = tf.paragraphs[ref.paragraph_index]
        except (IndexError, TypeError):
            return

        self._set_paragraph_text(para, block.target_text or "")
        self._apply_overflow(shape, block)

    @staticmethod
    def _set_paragraph_text(para, text: str) -> None:
        """Replace paragraph text, preserving the first run's formatting."""
        runs = para.runs
        if not runs:
            run = para.add_run()
            run.text = text
            return
        runs[0].text = text
        for extra in runs[1:]:
            extra.text = ""

    @staticmethod
    def _apply_overflow(shape, block: Block) -> None:
        if not block.constraints.can_shrink_font:
            return
        try:
            tf = shape.text_frame
            tf.word_wrap = True
            tf.auto_size = MSO_AUTO_SIZE.SHRINK_TEXT_ON_OVERFLOW
        except (AttributeError, ValueError):
            pass

    def _render_image(self, block: Block, index, images) -> None:
        ref = block.source_ref
        if ref.image_id is None:
            return
        res = images.get(ref.image_id)
        if res is None or not res.localized_data_ref:
            return
        shape = index.get((ref.slide_index, ref.shape_id))
        if shape is None or shape.shape_type != MSO_SHAPE_TYPE.PICTURE:
            return
        try:
            with open(res.localized_data_ref, "rb") as fh:
                new_blob = fh.read()
            self._replace_image_blob(shape, new_blob)
        except (AttributeError, OSError, KeyError, ValueError):
            pass

    @staticmethod
    def _replace_image_blob(shape, new_blob: bytes) -> None:
        """Replace the underlying image part blob for a picture shape.

        python-pptx 1.0+ exposes |Image| as an immutable value object, so we
        locate the actual |ImagePart| via the shape's blip relationship and
        overwrite its ``_blob``.
        """
        blip = next(shape._element.iter(_qtag(_NS_A, "blip")))
        rId = blip.attrib[_qtag(_NS_R, "embed")]
        image_part = shape.part.related_part(rId)
        image_part._blob = new_blob

    # ------------------------------------------------------------------ #
    # SmartArt (diagram) rendering
    # ------------------------------------------------------------------ #
    def _render_smartart(
        self,
        block: Block,
        index,
        smartart_cache: dict[object, ET.Element],
    ) -> None:
        if block.target_text is None:
            return
        ref = block.source_ref
        if ref.kind != "smartart_point" or not ref.region_id:
            return

        shape = index.get((ref.slide_index, ref.shape_id))
        if shape is None:
            return

        data_part = self._smartart_data_part(shape)
        if data_part is None:
            return

        root = smartart_cache.get(data_part)
        if root is None:
            try:
                root = ET.fromstring(data_part.blob)
                smartart_cache[data_part] = root
            except ET.ParseError:
                return

        model_id = ref.region_id
        for pt in root.findall(f".//{_qtag(_NS_DGM, 'pt')}"):
            if pt.get("modelId") == model_id:
                self._set_point_text(pt, block.target_text or "")
                break

    @staticmethod
    def _smartart_data_part(shape):
        relids = shape._element.find(f".//{_qtag(_NS_DGM, 'relIds')}")
        if relids is None:
            return None
        dm_rId = relids.attrib.get(_qtag(_NS_R, "dm"))
        if not dm_rId:
            return None
        return shape.part.related_part(dm_rId)

    @staticmethod
    def _set_point_text(pt, text: str) -> None:
        """Replace all text inside a diagram point with a single paragraph."""
        t_elem = pt.find(_qtag(_NS_DGM, "t"))
        if t_elem is None:
            return

        # Keep body properties / list style if present.
        body_pr = t_elem.find(_qtag(_NS_A, "bodyPr"))
        lst_style = t_elem.find(_qtag(_NS_A, "lstStyle"))
        t_elem.clear()
        if body_pr is not None:
            t_elem.append(body_pr)
        if lst_style is not None:
            t_elem.append(lst_style)

        para = ET.SubElement(t_elem, _qtag(_NS_A, "p"))
        run = ET.SubElement(para, _qtag(_NS_A, "r"))
        rPr = ET.SubElement(run, _qtag(_NS_A, "rPr"))
        rPr.set("lang", "zh-CN")
        text_elem = ET.SubElement(run, _qtag(_NS_A, "t"))
        text_elem.text = text

    @staticmethod
    def _persist_smartart(smartart_cache: dict[object, ET.Element]) -> None:
        """Write modified SmartArt XML back to their package parts."""
        for data_part, root in smartart_cache.items():
            xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            data_part._blob = xml_bytes


registry.register("renderer", "pptx")(PptxRenderer)
