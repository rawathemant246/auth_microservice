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


class DirectoryUser(BaseModel):
    """A user's display identity, for a service that stores none of its own."""

    user_id: int
    first_name: str
    last_name: Optional[str] = None
    username: str


class DirectoryResponse(BaseModel):
    """Names for one organization and some of its users.

    lms-backend holds no names: `student_profiles` has an `auth_user_id` and no
    `first_name`, and `school_profiles` has a board and an address but no school
    name. Anything it renders for a human — a report card, a class list, a
    certificate — has to resolve them here.

    The organization's own name comes back in the same response because a caller
    that needs a student's name almost always needs the school's too, and one round
    trip is cheaper than two.
    """

    organization_id: int
    organization_name: str
    users: list[DirectoryUser]
