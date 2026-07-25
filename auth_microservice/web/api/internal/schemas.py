"""Schemas for internal API endpoints."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class BulkUserEntry(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=128)
    last_name: Optional[str] = Field(None, max_length=128)
    username: str = Field(..., min_length=3, max_length=128)
    password: Optional[str] = Field(None, min_length=8, max_length=128)
    role_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None


class BulkUserCreateRequest(BaseModel):
    users: list[BulkUserEntry] = Field(..., min_length=1, max_length=500)


class BulkUserCreatedEntry(BaseModel):
    user_id: int
    username: str
    generated_password: Optional[str] = None


class BulkUserErrorEntry(BaseModel):
    index: int
    username: str
    error: str


class BulkUserCreateResponse(BaseModel):
    created: int
    failed: int
    errors: list[BulkUserErrorEntry]
    users: list[BulkUserCreatedEntry]


class UserPermissionsResponse(BaseModel):
    """Effective permissions for one user in one organization.

    Consumed by lms-backend, which caches the result briefly and authorizes
    locally against it rather than calling back on every request.
    """

    user_id: int
    organization_id: int
    role_id: Optional[int] = None
    role_name: Optional[str] = None
    permissions: list[str]
