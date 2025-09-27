"""Schemas for user management endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from auth_microservice.db.models.oltp import GenderEnum, UserStatusEnum
from auth_microservice.web.api.auth.schemas import ContactInformationInput


class UserCreateRequest(BaseModel):
    first_name: str
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    username: str = Field(..., min_length=3, max_length=128)
    password: str = Field(..., min_length=8, max_length=128)
    date_of_birth: Optional[str] = None
    gender: Optional[GenderEnum] = None
    nationality: Optional[str] = None
    role_id: Optional[int] = None
    contact_information: ContactInformationInput


class UserResponse(BaseModel):
    user_id: int
    username: str
    first_name: str
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    organization_id: int
    role_id: Optional[int] = None
    status: UserStatusEnum
    email: Optional[EmailStr] = None
    created_at: datetime
    updated_at: datetime


class UsersListResponse(BaseModel):
    items: list[UserResponse]


class UserUpdateRequest(BaseModel):
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[str] = None
    gender: Optional[GenderEnum] = None
    nationality: Optional[str] = None
    status: Optional[UserStatusEnum] = None
    role_id: Optional[int] = None


class UserContactResponse(BaseModel):
    email: EmailStr
    phone_number: Optional[str] = None
    emergency_number: Optional[str] = None
    address: Optional[str] = None
    street_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    country: Optional[str] = None


class UserContactUpdateRequest(BaseModel):
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    emergency_number: Optional[str] = None
    address: Optional[str] = None
    street_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    country: Optional[str] = None

