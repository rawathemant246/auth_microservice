"""Schemas for bootstrap endpoints."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from auth_microservice.db.models.oltp import GenderEnum, LicenseStatusEnum
from auth_microservice.web.api.auth.schemas import ContactInformationInput


class BootstrapAdminUser(BaseModel):
    first_name: str
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    username: str = Field(..., min_length=3, max_length=128)
    password: str = Field(..., min_length=8, max_length=128)
    date_of_birth: Optional[str] = None
    gender: Optional[GenderEnum] = None
    nationality: Optional[str] = None
    contact_information: ContactInformationInput


class BootstrapOrganizationRequest(BaseModel):
    organization_name: str = Field(..., min_length=1, max_length=100)
    license_status: Optional[LicenseStatusEnum] = None
    admin_user: BootstrapAdminUser


class BootstrapOrganizationResponse(BaseModel):
    organization_id: int
    organization_name: str
    admin_user_id: int
    admin_role_id: int
