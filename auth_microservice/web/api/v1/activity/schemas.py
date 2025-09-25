"""Schemas for activity endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from auth_microservice.db.models.oltp import LoginMethodEnum


class LoginActivityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    login_id: int
    user_id: int
    login_timestamp: datetime | None
    login_ip_address: str | None
    device_info: str | None
    login_success: bool
    failed_attempt_count: int | None
    login_method: LoginMethodEnum
    login_location: str | None


class LoginActivitiesResponse(BaseModel):
    items: list[LoginActivityResponse]


class UserActivityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    activity_id: int
    user_id: int
    activity_type: str
    activity_description: str | None
    activity_timestamp: datetime | None
    ip_address: str | None


class UserActivitiesResponse(BaseModel):
    items: list[UserActivityResponse]
