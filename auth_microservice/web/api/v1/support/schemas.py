"""Schemas for support ticket APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from auth_microservice.db.models.oltp import SupportPriorityEnum, TicketStatusEnum


class SupportTicketCreateRequest(BaseModel):
    subject: str = Field(..., min_length=3, max_length=100)
    description: str = Field(..., min_length=1)
    priority: SupportPriorityEnum = SupportPriorityEnum.MEDIUM


class SupportTicketUpdateRequest(BaseModel):
    subject: Optional[str] = Field(default=None, min_length=3, max_length=100)
    description: Optional[str] = None
    priority: Optional[SupportPriorityEnum] = None
    status: Optional[TicketStatusEnum] = None


class SupportTicketUser(BaseModel):
    user_id: int
    first_name: str
    last_name: Optional[str] = None


class SupportTicketResponse(BaseModel):
    ticket_id: int
    subject: str
    description: str
    priority: SupportPriorityEnum
    status: TicketStatusEnum
    created_at: datetime | None
    updated_at: datetime | None
    user: SupportTicketUser


class SupportTicketsListResponse(BaseModel):
    items: list[SupportTicketResponse]


class SupportTicketCommentCreateRequest(BaseModel):
    comment: str = Field(..., min_length=1)


class SupportTicketCommentResponse(BaseModel):
    comment_id: int
    comment: str
    created_at: datetime | None
    user: SupportTicketUser


class SupportTicketCommentsListResponse(BaseModel):
    items: list[SupportTicketCommentResponse]

