"""Schemas for document-backed settings endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class OrganizationSettingsResponse(BaseModel):
    organization_id: int
    settings: dict[str, Any] | None


class PrivacySettingsResponse(BaseModel):
    organization_id: int
    settings: dict[str, Any] | None


class UserFeedbackResponse(BaseModel):
    organization_id: int
    feedback: list[dict[str, Any]]
