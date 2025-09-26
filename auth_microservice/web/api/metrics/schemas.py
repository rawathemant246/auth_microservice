"""Schemas for metrics ingestion APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class SystemHealthIngestRequest(BaseModel):
    organization_id: int
    server_uptime: Optional[float] = Field(default=None, ge=0.0)
    active_users: Optional[int] = Field(default=None, ge=0)
    storage_usage: Optional[float] = Field(default=None, ge=0.0)
    cpu_usage: Optional[float] = Field(default=None, ge=0.0)
    memory_usage: Optional[float] = Field(default=None, ge=0.0)
    log_date: Optional[datetime] = None


class SystemHealthIngestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    log_id: int


class SystemAlertIngestRequest(BaseModel):
    organization_id: int
    alert_type: str = Field(..., min_length=1, max_length=50)
    alert_message: str = Field(..., min_length=1)
    resolved: Optional[bool] = False
    alert_date: Optional[datetime] = None


class SystemAlertIngestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    alert_id: int


class UsageMetricIngestRequest(BaseModel):
    organization_id: int
    metric_date: Optional[datetime] = None
    active_users: Optional[int] = Field(default=None, ge=0)
    storage_used: Optional[int] = Field(default=None, ge=0)


class UsageMetricIngestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    metric_id: int
