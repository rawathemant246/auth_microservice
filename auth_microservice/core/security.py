"""Security helpers for password hashing and JWT creation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import jwt
from passlib.context import CryptContext

from auth_microservice.settings import settings


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a plain text password."""

    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""

    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    subject: str,
    expires_minutes: int | None = None,
    claims: dict[str, Any] | None = None,
) -> str:
    """Create a signed JWT access token."""

    expire_minutes = expires_minutes or settings.jwt_access_token_expires_minutes
    expire_at = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)
    payload: dict[str, Any] = {"sub": subject, "exp": expire_at}
    if claims:
        payload.update(claims)
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    """Decode a JWT token returning its payload."""

    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
