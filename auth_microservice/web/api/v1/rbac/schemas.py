"""Schemas for RBAC administration endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class RoleCreateRequest(BaseModel):
    role_name: str = Field(..., min_length=1, max_length=50)
    role_description: Optional[str] = Field(default=None, max_length=255)


class RoleUpdateRequest(BaseModel):
    role_name: Optional[str] = Field(default=None, min_length=1, max_length=50)
    role_description: Optional[str] = Field(default=None, max_length=255)


class RoleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role_id: int
    organization_id: int
    role_name: str
    role_description: Optional[str]
    permissions: list[int]
    created_at: datetime
    updated_at: datetime


class RolesListResponse(BaseModel):
    items: list[RoleResponse]


class PermissionCreateRequest(BaseModel):
    permission_name: str = Field(..., min_length=1, max_length=50)
    permission_description: Optional[str] = Field(default=None, max_length=255)


class PermissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    permission_id: int
    permission_name: str
    permission_description: Optional[str]
    created_at: datetime


class PermissionsListResponse(BaseModel):
    items: list[PermissionResponse]


class RolePermissionAssignRequest(BaseModel):
    permission_id: int


class UserRoleAssignRequest(BaseModel):
    role_id: int


class EffectivePermissionsResponse(BaseModel):
    permissions: list[str]

