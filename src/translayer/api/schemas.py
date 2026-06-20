"""Request/response DTOs for the API."""

from __future__ import annotations

from pydantic import BaseModel


class BlockEdit(BaseModel):
    target_text: str


class RegionEdit(BaseModel):
    target_text: str


class JobSummary(BaseModel):
    id: str
    state: str
    error: str | None = None
    source_lang: str
    target_lang: str
    blocks: int
    images: int
    has_output: bool
