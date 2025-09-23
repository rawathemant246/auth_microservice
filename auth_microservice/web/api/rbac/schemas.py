"""Schemas for RBAC endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RbacCheckRequest(BaseModel):
    user_id: int
    organization_id: int
    permission_name: str = Field(..., alias="permission")

    model_config = {
        "populate_by_name": True,
    }


class RbacCheckRequest(BaseModel):
    user_id: int
    organization_id: int
    permission_name: str = Field(..., alias="permission")


class RbacCheckResponse(BaseModel):
    allowed: bool


class UserPermissionsResponse(BaseModel):
    permissions: list[str]
