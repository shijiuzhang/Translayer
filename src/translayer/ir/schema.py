"""Export the DocumentIR JSON Schema — the open-standard artifact."""

from __future__ import annotations

import json
from typing import Any

from translayer.ir.models import DocumentIR


def ir_json_schema() -> dict[str, Any]:
    return DocumentIR.model_json_schema()


def dump_schema(indent: int = 2) -> str:
    return json.dumps(ir_json_schema(), indent=indent, ensure_ascii=False)
