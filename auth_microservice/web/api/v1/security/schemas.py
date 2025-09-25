"""Schemas for security alert endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from auth_microservice.db.models.oltp import AlertStatusEnum


class SecurityAlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    alert_id: int
    user_id: int
    alert_type: str
    alert_message: str
    alert_status: AlertStatusEnum
    created_at: datetime | None
    resolved_at: datetime | None


class SecurityAlertsResponse(BaseModel):
    items: list[SecurityAlertResponse]


class SecurityAlertUpdateRequest(BaseModel):
    alert_status: AlertStatusEnum | None = None
    alert_message: str | None = None
    resolved_at: datetime | None = None
