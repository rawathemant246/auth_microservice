"""Pydantic models for versioned auth API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, HttpUrl

from auth_microservice.db.models.oltp import UserStatusEnum


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=128)
    password: str = Field(..., min_length=8, max_length=128)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Access token expiry in seconds")
    refresh_expires_at: datetime
    session_id: int


class UserProfileResponse(BaseModel):
    user_id: int
    username: str
    first_name: str
    last_name: str | None = None
    organization_id: int
    role_id: int | None = None
    email: EmailStr | None = None
    status: UserStatusEnum


class LoginResponse(BaseModel):
    tokens: TokenPair
    user: UserProfileResponse


class LogoutResponse(BaseModel):
    status: str = "success"


class RefreshRequest(BaseModel):
    session_id: int
    refresh_token: str


class RefreshResponse(BaseModel):
    tokens: TokenPair
    user: UserProfileResponse


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    status: str = "ok"
    reset_token: str | None = None


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8, max_length=128)


class ResetPasswordResponse(BaseModel):
    status: str = "ok"


class ProvidersResponse(BaseModel):
    providers: list[str]


class SsoCallbackQueryParams(BaseModel):
    code: str
    state: str
    redirect_uri: HttpUrl


class SsoCallbackResponse(BaseModel):
    tokens: TokenPair
    user: UserProfileResponse


class SsoLinkRequest(BaseModel):
    code: str
    state: str
    redirect_uri: HttpUrl


class SsoLinkResponse(BaseModel):
    status: str = "linked"


class SsoUnlinkResponse(BaseModel):
    status: str = "unlinked"
