from __future__ import annotations

import re
from collections.abc import Sequence

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
    min_size: int = 8,
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
        if width <= box_w and height <= box_h:
            best_size = size
            best_lines = lines
            low = size + 1
        else:
            high = size - 1

    if best_lines is not None:
        return best_size, best_lines

    font = ImageFont.truetype(font_path, size=best_size)
    return best_size, wrap_text(text, font, box_w, draw)


def render_text_in_box(img: Image.Image, region: ImageTextRegion, lang: str | None = None) -> None:
    """Render translated region text into its bbox with real-font wrapping and shrink-to-fit."""
    text = region.target_text or region.source_text
    if not text:
        return

    bbox = region.bbox
    box_w = max(0, int(bbox.w))
    box_h = max(0, int(bbox.h))
    if box_w == 0 or box_h == 0:
        return

    resolved_lang = lang or ("zh" if _CJK_RE.search(text) else "en")
    registry = FontRegistry()
    font_path = registry.font_for_lang(resolved_lang)
    estimated_size = region.font_estimate.size or min(box_h, 32)
    max_size = max(8, int(round(estimated_size)))
    size, lines = fit_text(text, box_w, box_h, font_path, max_size=max_size)
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
