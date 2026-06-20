from __future__ import annotations

import base64
import json
import re
from typing import Any

import httpx
from PIL import Image

from translayer.config import settings
from translayer.engines.ocr.base import BaseOCREngine, image_mime_type
from translayer.ir.models import ImageTextRegion
from translayer.plugins import registry


@registry.register("ocr", "cloud_vision")
class CloudVisionEngine(BaseOCREngine):
    name = "cloud_vision"

    def detect(self, image_path: str) -> list[ImageTextRegion]:
        if not settings.vision_api_key:
            raise RuntimeError("Cloud vision OCR requires settings.vision_api_key / OPENAI_API_KEY.")

        with Image.open(image_path) as img:
            width, height = img.size
        with open(image_path, "rb") as fh:
            encoded = base64.b64encode(fh.read()).decode("ascii")

        response = httpx.post(
            f"{settings.vision_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.vision_api_key}"},
            json={
                "model": settings.vision_model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are an OCR engine. Return only valid JSON: an array of objects "
                            "with text, bbox {x,y,w,h} in pixels, optional color (#RRGGBB), "
                            "and optional align (left, center, right)."
                        ),
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    f"Detect all translatable text in this {width}x{height} image. "
                                    "Use pixel coordinates relative to the original image."
                                ),
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{image_mime_type(image_path)};base64,{encoded}"
                                },
                            },
                        ],
                    },
                ],
                "temperature": 0,
            },
            timeout=60,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return self._regions_from_payload(image_path, content)

    def _regions_from_payload(self, image_path: str, content: str | list[Any]) -> list[ImageTextRegion]:
        if isinstance(content, list):
            content = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
        data = _loads_json_array(str(content))
        regions: list[ImageTextRegion] = []
        for idx, item in enumerate(data, start=1):
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or item.get("source_text") or "").strip()
            bbox = item.get("bbox") or {}
            if not text or not isinstance(bbox, dict):
                continue
            try:
                x = int(round(float(bbox["x"])))
                y = int(round(float(bbox["y"])))
                w = int(round(float(bbox["w"])))
                h = int(round(float(bbox["h"])))
            except (KeyError, TypeError, ValueError):
                continue
            if w <= 0 or h <= 0:
                continue
            align = item.get("align") if item.get("align") in {"left", "center", "right"} else "left"
            color = item.get("color") or item.get("font_color")
            region = self.make_region(idx, x, y, w, h, text, image_path=image_path, align=align)
            if _is_hex_color(color):
                region.font_estimate.color = str(color)
            regions.append(region)
        return regions


def _loads_json_array(content: str) -> list[Any]:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\[[\s\S]*\]", stripped)
        if not match:
            return []
        data = json.loads(match.group(0))
    if isinstance(data, dict):
        data = data.get("regions", [])
    return data if isinstance(data, list) else []


def _is_hex_color(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value) is not None
