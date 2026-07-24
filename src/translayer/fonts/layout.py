from __future__ import annotations

import re
from collections.abc import Sequence
from math import ceil
from statistics import median

from PIL import Image, ImageDraw, ImageFont

from translayer.fonts.registry import FontRegistry
from translayer.ir.models import ImageTextRegion

_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]")
_DEFAULT_COLOR = (24, 24, 24)


def _text_width(text: str, font: ImageFont.FreeTypeFont, draw: ImageDraw.ImageDraw) -> float:
    if hasattr(font, "getlength"):
        return float(font.getlength(text))
    bbox = draw.textbbox((0, 0), text, font=font)
    return float(bbox[2] - bbox[0])


def _wrap_token(token: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in token:
        trial = f"{current}{char}"
        if current and _text_width(trial, font, draw) > max_width:
            lines.append(current)
            current = char
        else:
            current = trial
    if current:
        lines.append(current)
    return lines or [token]


def wrap_text(
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    draw: ImageDraw.ImageDraw,
) -> list[str]:
    """Greedy wrap spaced text; fall back to character wrapping for CJK/no-space text."""
    if "\n" in (text or ""):
        lines: list[str] = []
        for paragraph in text.splitlines():
            if not paragraph.strip():
                lines.append("")
                continue
            lines.extend(wrap_text(paragraph, font, max_width, draw))
        return lines or [""]

    normalized = " ".join((text or "").split())
    if not normalized:
        return [""]
    if max_width <= 0:
        return [normalized]

    if " " not in normalized or _CJK_RE.search(normalized):
        return _wrap_token(normalized, font, max_width, draw)

    lines: list[str] = []
    current = ""
    for word in normalized.split(" "):
        trial = word if not current else f"{current} {word}"
        if _text_width(trial, font, draw) <= max_width:
            current = trial
            continue
        if current:
            lines.append(current)
        if _text_width(word, font, draw) > max_width:
            broken = _wrap_token(word, font, max_width, draw)
            lines.extend(broken[:-1])
            current = broken[-1]
        else:
            current = word
    if current:
        lines.append(current)
    return lines


def _latin_words_fit(
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    draw: ImageDraw.ImageDraw,
) -> bool:
    if _CJK_RE.search(text or ""):
        return True
    words = (text or "").replace("\n", " ").split()
    return not words or max(_text_width(word, font, draw) for word in words) <= max_width


def _block_size(
    lines: Sequence[str],
    font: ImageFont.FreeTypeFont,
    draw: ImageDraw.ImageDraw,
    spacing: int = 2,
) -> tuple[int, int]:
    if not lines:
        return 0, 0
    text = "\n".join(lines)
    bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=spacing)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _line_spacing(size: int) -> int:
    return max(1, size // 8)


def fit_text(
    text: str,
    box_w: int,
    box_h: int,
    font_path: str,
    max_size: int,
    min_size: int = 5,
) -> tuple[int, list[str]]:
    """Return the largest font size whose wrapped text block fits the box."""
    probe = Image.new("RGB", (max(1, box_w), max(1, box_h)), "white")
    draw = ImageDraw.Draw(probe)
    low = max(1, int(min_size))
    high = max(low, int(max_size))
    best_size = low
    best_lines: list[str] | None = None

    while low <= high:
        size = (low + high) // 2
        font = ImageFont.truetype(font_path, size=size)
        lines = wrap_text(text, font, box_w, draw)
        width, height = _block_size(lines, font, draw, spacing=_line_spacing(size))
        if (
            width <= box_w
            and height <= box_h
            and _latin_words_fit(text, font, box_w, draw)
        ):
            best_size = size
            best_lines = lines
            low = size + 1
        else:
            high = size - 1

    if best_lines is not None:
        return best_size, best_lines

    font = ImageFont.truetype(font_path, size=best_size)
    return best_size, wrap_text(text, font, box_w, draw)


def text_fits_in_box(
    text: str,
    box_w: int,
    box_h: int,
    font_path: str,
    max_size: int,
    min_size: int = 5,
) -> bool:
    """Return whether text can be rendered without escaping the target box."""
    size, lines = fit_text(
        text,
        box_w,
        box_h,
        font_path,
        max_size=max_size,
        min_size=min_size,
    )
    probe = Image.new("RGB", (max(1, box_w), max(1, box_h)), "white")
    draw = ImageDraw.Draw(probe)
    font = ImageFont.truetype(font_path, size=size)
    width, height = _block_size(lines, font, draw, spacing=_line_spacing(size))
    return width <= box_w and height <= box_h


def region_text_fits(region: ImageTextRegion, lang: str | None = None) -> bool:
    text = region.target_text or region.source_text
    if not text:
        return True
    box_w = max(0, int(region.bbox.w))
    box_h = max(0, int(region.bbox.h))
    if box_w == 0 or box_h == 0:
        return False
    resolved_lang = lang or ("zh" if _CJK_RE.search(text) else "en")
    font_path = FontRegistry().font_for_lang(resolved_lang)
    estimated_size = region.font_estimate.size or min(box_h, 32)
    return text_fits_in_box(
        text,
        box_w,
        box_h,
        font_path,
        max_size=max(5, int(round(estimated_size))),
    )


def render_text_canvas(
    size: tuple[int, int],
    regions: Sequence[ImageTextRegion],
    lang: str,
) -> Image.Image:
    """Reflow dense OCR translations onto a clean canvas.

    This is intended for screenshots whose meaningful content is the text
    itself. It avoids preserving missed source glyphs and gives longer target
    languages the full image area instead of the original per-line boxes.
    """
    width, height = size
    texts = [
        region.target_text.strip()
        for region in regions
        if region.target_text and region.target_text.strip()
    ]
    if not texts:
        return Image.new("RGB", size, (248, 249, 251))

    registry = FontRegistry()
    font_path = registry.font_for_lang(lang)
    source_sizes = [
        region.font_estimate.size
        for region in regions
        if region.font_estimate.size and region.font_estimate.size > 0
    ]
    max_size = max(14, min(36, int(round(median(source_sizes))) if source_sizes else 24))
    padding = max(10, int(round(min(width, height) * 0.035)))
    gap = max(12, padding)
    columns = _text_canvas_columns(width, height, sum(len(text) for text in texts))
    column_width = max(1, (width - 2 * padding - (columns - 1) * gap) // columns)
    content_height = max(1, height - 2 * padding)

    size_px, lines, line_height, required_height = _fit_canvas_lines(
        texts,
        font_path,
        column_width,
        content_height,
        columns,
        max_size=max_size,
    )
    canvas_height = max(height, required_height + 2 * padding)
    image = Image.new("RGB", (width, canvas_height), (248, 249, 251))
    font = ImageFont.truetype(font_path, size=size_px)
    draw = ImageDraw.Draw(image)
    lines_per_column = max(1, ceil(len(lines) / columns))
    for index, line in enumerate(lines):
        column = min(columns - 1, index // lines_per_column)
        row = index % lines_per_column
        x = padding + column * (column_width + gap)
        y = padding + row * line_height
        draw.text((x, y), line, font=font, fill=(22, 27, 34))
    return image


def _text_canvas_columns(width: int, height: int, text_length: int) -> int:
    ratio = width / max(1, height)
    if ratio >= 4.0 and text_length >= 200:
        return 3
    if ratio >= 1.8 and text_length >= 100:
        return 2
    return 1


def _fit_canvas_lines(
    texts: Sequence[str],
    font_path: str,
    column_width: int,
    content_height: int,
    columns: int,
    *,
    max_size: int,
    min_size: int = 3,
) -> tuple[int, list[str], int, int]:
    probe = Image.new("RGB", (max(1, column_width), max(1, content_height)), "white")
    draw = ImageDraw.Draw(probe)
    best: tuple[int, list[str], int] | None = None
    for size in range(max_size, min_size - 1, -1):
        font = ImageFont.truetype(font_path, size=size)
        lines: list[str] = []
        for text in texts:
            lines.extend(wrap_text(text, font, column_width, draw))
        line_height = max(
            1,
            draw.textbbox((0, 0), "Ag", font=font)[3]
            - draw.textbbox((0, 0), "Ag", font=font)[1]
            + _line_spacing(size),
        )
        capacity = max(1, content_height // line_height) * columns
        words_fit = all(
            _latin_words_fit(text, font, column_width, draw) for text in texts
        )
        if len(lines) <= capacity and words_fit:
            return size, lines, line_height, content_height
        best = (size, lines, line_height)
    assert best is not None
    size, lines, line_height = best
    required_height = ceil(len(lines) / columns) * line_height
    return size, lines, line_height, required_height


def render_text_in_box(
    img: Image.Image, region: ImageTextRegion, lang: str | None = None
) -> bool:
    """Render translated region text into its bbox with real-font wrapping and shrink-to-fit."""
    text = region.target_text or region.source_text
    if not text:
        return True

    bbox = region.bbox
    box_w = max(0, int(bbox.w))
    box_h = max(0, int(bbox.h))
    if box_w == 0 or box_h == 0:
        return False

    resolved_lang = lang or ("zh" if _CJK_RE.search(text) else "en")
    registry = FontRegistry()
    font_path = registry.font_for_lang(resolved_lang)
    estimated_size = region.font_estimate.size or min(box_h, 32)
    max_size = max(5, int(round(estimated_size)))
    size, lines = fit_text(text, box_w, box_h, font_path, max_size=max_size)
    if not text_fits_in_box(text, box_w, box_h, font_path, max_size=max_size):
        return False
    font = ImageFont.truetype(font_path, size=size)

    overlay = Image.new("RGBA", (box_w, box_h), (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)
    spacing = _line_spacing(size)
    block_w, block_h = _block_size(lines, font, draw, spacing=spacing)
    y = max(0, (box_h - block_h) // 2)
    color = _parse_color(region.font_estimate.color)

    for line in lines:
        line_bbox = draw.textbbox((0, 0), line, font=font)
        line_w = line_bbox[2] - line_bbox[0]
        if region.align == "center":
            x = max(0, (box_w - line_w) // 2)
        elif region.align == "right":
            x = max(0, box_w - line_w)
        else:
            x = 0
        draw.text((x - line_bbox[0], y - line_bbox[1]), line, font=font, fill=color)
        y += line_bbox[3] - line_bbox[1] + spacing

    if img.mode == "RGBA":
        img.alpha_composite(overlay, (int(bbox.x), int(bbox.y)))
    else:
        img.paste(Image.alpha_composite(img.crop((bbox.x, bbox.y, bbox.x + box_w, bbox.y + box_h)).convert("RGBA"), overlay).convert(img.mode), (int(bbox.x), int(bbox.y)))
    return True


def _parse_color(color: str | None) -> tuple[int, int, int, int]:
    if not color:
        return (*_DEFAULT_COLOR, 255)
    value = color.strip()
    if value.startswith("#"):
        value = value[1:]
    if len(value) == 3:
        value = "".join(char * 2 for char in value)
    if len(value) != 6:
        return (*_DEFAULT_COLOR, 255)
    try:
        red = int(value[0:2], 16)
        green = int(value[2:4], 16)
        blue = int(value[4:6], 16)
    except ValueError:
        return (*_DEFAULT_COLOR, 255)
    return red, green, blue, 255
