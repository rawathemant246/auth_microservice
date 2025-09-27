"""Reusable API dependencies for authentication and RBAC enforcement."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, Header, HTTPException, Request, status
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.core.security import decode_token
from auth_microservice.db.dependencies import get_db_session
from auth_microservice.db.models.oltp import User
from auth_microservice.services.auth.service import AuthService


@dataclass
class AuthenticatedPrincipal:
    """Authenticated user context derived from a bearer token."""

    user_id: int
    session_id: int
    organization_id: int
    role_id: int | None
    status: str
    username: str
    token_payload: dict[str, Any]
    raw_token: str


async def get_current_principal(
    authorization: str | None = Header(default=None, alias="Authorization"),
    session: AsyncSession = Depends(get_db_session),
) -> AuthenticatedPrincipal:
    """Resolve the bearer token into a user and active session."""

    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not_authenticated")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_authorization_header")

    try:
        payload = decode_token(token)
    except JWTError as exc:  # - intentionally masking token parsing issues
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_token") from exc

    subject = payload.get("sub")
    session_id = payload.get("session_id")
    if subject is None or session_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_token_payload")

    try:
        user_id = int(subject)
        session_pk = int(session_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_token_payload") from exc

    auth_service = AuthService(session)
    session_record = await auth_service.get_session(session_pk)
    if session_record is None or session_record.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="session_not_found")

    if session_record.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="session_revoked")

    now = datetime.now(timezone.utc)
    if session_record.refresh_token_expires_at < now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="session_expired")

    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user_not_found")

    return AuthenticatedPrincipal(
        user_id=user.user_id,
        session_id=session_record.login_id,
        organization_id=user.organization_id,
        role_id=user.role_id,
        status=user.status.value if hasattr(user.status, "value") else str(user.status),
        username=user.username,
        token_payload=payload,
        raw_token=token,
    )


def require_permission(permission_name: str):
    """Factory returning a dependency enforcing a permission via RBAC service."""

    async def _dependency(
        request: Request,
        principal: AuthenticatedPrincipal = Depends(get_current_principal),
    ) -> AuthenticatedPrincipal:
        rbac_service = request.app.state.rbac_service
        allowed = await rbac_service.enforce(
            user_id=principal.user_id,
            permission_name=permission_name,
            organization_id=principal.organization_id,
        )
        if not allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
        return principal

    return _dependency


def require_permissions(*permission_names: str):
    """Ensure the principal has every listed permission within their organization."""

    async def _dependency(
        request: Request,
        principal: AuthenticatedPrincipal = Depends(get_current_principal),
    ) -> AuthenticatedPrincipal:
        rbac_service = request.app.state.rbac_service
        for permission_name in permission_names:
            allowed = await rbac_service.enforce(
                user_id=principal.user_id,
                permission_name=permission_name,
                organization_id=principal.organization_id,
            )
            if not allowed:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
        return principal

    return _dependency
