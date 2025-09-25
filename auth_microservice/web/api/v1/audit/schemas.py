"""Schemas for audit log endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    log_id: int
    user_id: int
    action_type: str
    action_description: str | None
    affected_table: str | None
    affected_row_id: int | None
    previous_data: dict[str, Any] | None
    new_data: dict[str, Any] | None
    ip_address: str | None
    action_timestamp: datetime | None


class AuditLogsResponse(BaseModel):
    items: list[AuditLogResponse]
