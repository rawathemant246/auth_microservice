"""Schemas for feedback APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class FeedbackCreateRequest(BaseModel):
    organization_id: int
    content: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)
    status: str = "new"


class FeedbackResponse(BaseModel):
    feedback_id: str
    organization_id: int
    user_id: int
    content: str
    category: str
    status: str
    created_at: datetime | str | None = None
    updated_at: datetime | str | None = None


class FeedbackListResponse(BaseModel):
    items: list[FeedbackResponse]


class FeedbackUpdateRequest(BaseModel):
    content: Optional[str] = None
    category: Optional[str] = None
    status: Optional[str] = None
