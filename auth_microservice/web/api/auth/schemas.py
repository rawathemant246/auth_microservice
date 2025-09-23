"""Pydantic schemas for authentication and SSO flows."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, EmailStr, Field, HttpUrl

from auth_microservice.db.models.oltp import GenderEnum


class ContactInformationInput(BaseModel):
    email: EmailStr
    phone_number: Optional[str] = None
    emergency_number: Optional[str] = None
    address: Optional[str] = None
    street_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    country: Optional[str] = None


class UserRegistrationRequest(BaseModel):
    first_name: str
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    username: str = Field(..., min_length=3, max_length=128)
    password: str = Field(..., min_length=8, max_length=128)
    date_of_birth: Optional[str] = None
    gender: Optional[GenderEnum] = None
    organization_id: int
    role_id: Optional[int] = None
    nationality: Optional[str] = None
    contact_information: ContactInformationInput


class UserResponse(BaseModel):
    user_id: int
    username: str
    first_name: str
    last_name: Optional[str]
    organization_id: int
    role_id: Optional[int]
    email: EmailStr


class UserLoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class GoogleSsoLoginResponse(BaseModel):
    login_url: HttpUrl
    state: str


class GoogleSsoCallbackRequest(BaseModel):
    code: str
    state: str
    redirect_uri: HttpUrl


class GoogleSsoCallbackResponse(BaseModel):
    token: TokenResponse
    user: UserResponse
