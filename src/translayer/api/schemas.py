"""Request/response DTOs for the API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ImageDecisionAction = Literal["preserve", "whole_image", "region", "logo", "reuse"]


class BlockEdit(BaseModel):
    target_text: str


class RegionEdit(BaseModel):
    target_text: str


class ImageDecisionEdit(BaseModel):
    action: ImageDecisionAction


class BulkImageDecisionEdit(BaseModel):
    image_ids: list[str] = Field(min_length=1)
    action: ImageDecisionAction


class ApproveImagePlan(BaseModel):
    allow_paid_api: bool = False
    max_budget_usd: float = Field(default=0.0, ge=0.0)
    gemini_api_key: str | None = None
    gemini_model: str | None = None


class JobSummary(BaseModel):
    id: str
    state: str
    error: str | None = None
    source_lang: str
    target_lang: str
    blocks: int
    images: int
    has_output: bool
