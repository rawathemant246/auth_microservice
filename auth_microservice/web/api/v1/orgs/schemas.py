"""Schemas for organization management endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from auth_microservice.db.models.oltp import GenderEnum, LicenseStatusEnum
from auth_microservice.web.api.auth.schemas import ContactInformationInput


class OrganizationCreateRequest(BaseModel):
    organization_name: str = Field(..., min_length=1, max_length=100)
    license_status: Optional[LicenseStatusEnum] = None


class OrganizationUpdateRequest(BaseModel):
    organization_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    license_status: Optional[LicenseStatusEnum] = None


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    organization_id: int
    organization_name: str
    license_status: LicenseStatusEnum
    created_at: datetime
    updated_at: datetime


class OrganizationsListResponse(BaseModel):
    items: list[OrganizationResponse]


class AdminUserCreateRequest(BaseModel):
    first_name: str
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    username: str = Field(..., min_length=3, max_length=128)
    password: str = Field(..., min_length=8, max_length=128)
    date_of_birth: Optional[str] = None
    gender: Optional[GenderEnum] = None
    nationality: Optional[str] = None
    contact_information: ContactInformationInput


class AdminUserResponse(BaseModel):
    user_id: int
    username: str
    email: EmailStr
    first_name: str
    last_name: Optional[str]
    organization_id: int
    role_id: int


class OrganizationSettingsUpdateRequest(BaseModel):
    settings: dict[str, Any]


class PrivacySettingsUpdateRequest(BaseModel):
    settings: dict[str, Any]
