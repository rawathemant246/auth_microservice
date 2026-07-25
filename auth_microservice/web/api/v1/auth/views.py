"""Versioned authentication and SSO endpoints."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from redis.asyncio import Redis
from redis.asyncio.connection import ConnectionPool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.db.dependencies import get_db_session
from auth_microservice.db.models.oltp import ContactInformation, SsoProvider, SsoProviderName, User
from auth_microservice.services.auth.service import AuthService
from auth_microservice.services.events import (
    publish_email_event,
    publish_security_event,
)
from auth_microservice.services.redis.dependency import get_redis_pool
from auth_microservice.services.sso import CasdoorService
from auth_microservice.web.api.dependencies import (
    AuthenticatedPrincipal,
    get_current_principal,
)
from auth_microservice.web.api.v1.auth.schemas import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    LoginResponse,
    LogoutResponse,
    ProvidersResponse,
    RefreshRequest,
    RefreshResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    SsoCallbackQueryParams,
    SsoCallbackResponse,
    SsoLinkRequest,
    SsoLinkResponse,
    SsoUnlinkResponse,
    TokenPair,
    UserProfileResponse,
)

router = APIRouter(prefix="/v1/auth", tags=["auth"])


def _get_client_ip(request: Request) -> str | None:
    if request.client and request.client.host:
        return request.client.host
    return request.headers.get("x-forwarded-for")


def _get_user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


async def _check_login_rate_limit(
    request: Request,
    redis_pool: ConnectionPool = Depends(get_redis_pool),
) -> None:
    """Rate limit login attempts: max 10 per IP per 5 minutes."""
    redis = Redis(connection_pool=redis_pool)
    ip = request.client.host if request.client else "unknown"
    key = f"login_rate_limit:{ip}"

    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 300)  # 5 minute window

    if count > 10:
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Try again in 5 minutes.",
        )


async def _resolve_email(
    session: AsyncSession,
    user_id: int,
    fallback: str | None = None,
) -> str | None:
    if fallback:
        return fallback
    stmt = select(ContactInformation.email_id).where(ContactInformation.user_id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _build_user_profile(
    session: AsyncSession,
    user: User,
    email: str | None = None,
) -> UserProfileResponse:
    email_value = await _resolve_email(session, user.user_id, fallback=email)
    return UserProfileResponse(
        user_id=user.user_id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        organization_id=user.organization_id,
        role_id=user.role_id,
        email=email_value,
        status=user.status,
    )


def _build_token_pair(data: dict) -> TokenPair:
    expires_seconds = data["access_token_expires_minutes"] * 60
    refresh_expires_at: datetime = data["refresh_token_expires_at"]
    session = data["session"]
    return TokenPair(
        access_token=data["access_token"],
        refresh_token=data["refresh_token"],
        expires_in=expires_seconds,
        refresh_expires_at=refresh_expires_at,
        session_id=session.login_id,
    )


def _get_casdoor_service(request: Request) -> CasdoorService:
    service: CasdoorService = request.app.state.casdoor_service
    return service


async def _check_forgot_password_rate_limit(
    request: Request,
    redis_pool: ConnectionPool = Depends(get_redis_pool),
) -> None:
    """Rate limit forgot-password: max 5 per email/IP per 15 minutes."""
    redis = Redis(connection_pool=redis_pool)
    ip = request.client.host if request.client else "unknown"
    key = f"forgot_pwd_rate_limit:{ip}"

    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 900)  # 15 minute window

    if count > 5:
        raise HTTPException(
            status_code=429,
            detail="Too many password reset attempts. Try again later.",
        )


def _parse_org_and_nonce_from_state(state: str) -> tuple[int, str]:
    """Parse state format: org:<org_id>:nonce:<nonce>"""
    parts = state.split(":")
    if len(parts) != 4 or parts[0] != "org" or parts[2] != "nonce":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_state")
    try:
        org_id = int(parts[1])
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_state") from exc
    return org_id, parts[3]


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    _rate_limit: None = Depends(_check_login_rate_limit),
) -> LoginResponse:
    auth_service = AuthService(session)
    try:
        user, email = await auth_service.authenticate_user(
            payload.username,
            payload.password,
            ip_address=_get_client_ip(request),
            user_agent=_get_user_agent(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    session_data = await auth_service.create_session(
        user,
        email,
        ip_address=_get_client_ip(request),
        user_agent=_get_user_agent(request),
    )
    profile = await _build_user_profile(session, user, email)
    tokens = _build_token_pair(session_data)
    session_record = session_data["session"]
    await publish_security_event(
        request,
        "auth.login",
        {
            "user_id": user.user_id,
            "organization_id": user.organization_id,
            "session_id": session_record.login_id,
            "ip": _get_client_ip(request),
        },
    )
    return LoginResponse(tokens=tokens, user=profile)


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> LogoutResponse:
    auth_service = AuthService(session)
    session_record = await auth_service.get_session(principal.session_id)
    if session_record is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="session_not_found")
    await auth_service.revoke_session(session_record)
    await publish_security_event(
        request,
        "auth.logout",
        {
            "user_id": principal.user_id,
            "organization_id": principal.organization_id,
            "session_id": session_record.login_id,
        },
    )
    return LogoutResponse()


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_token(
    payload: RefreshRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> RefreshResponse:
    auth_service = AuthService(session)
    session_record = await auth_service.get_session(payload.session_id)
    if session_record is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="session_not_found")

    try:
        refreshed = await auth_service.refresh_session(
            session_record,
            payload.refresh_token,
            ip_address=_get_client_ip(request),
            user_agent=_get_user_agent(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    tokens = _build_token_pair(
        {
            "session": session_record,
            "access_token": refreshed["access_token"],
            "access_token_expires_minutes": refreshed["access_token_expires_minutes"],
            "refresh_token": refreshed["refresh_token"],
            "refresh_token_expires_at": refreshed["refresh_token_expires_at"],
        },
    )
    profile = await _build_user_profile(session, refreshed["user"], refreshed.get("email"))
    return RefreshResponse(tokens=tokens, user=profile)


@router.post("/password/forgot", response_model=ForgotPasswordResponse)
async def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    redis_pool: ConnectionPool = Depends(get_redis_pool),
    _rate_limit: None = Depends(_check_forgot_password_rate_limit),
) -> ForgotPasswordResponse:
    auth_service = AuthService(session)
    redis = Redis(connection_pool=redis_pool)
    token = await auth_service.create_password_reset_token(payload.email, redis=redis)
    if token:
        await publish_email_event(
            request,
            "password.reset",
            {"email": payload.email, "token": token},
        )
    # Never leak whether the user exists nor expose the raw token.
    return ForgotPasswordResponse(status="ok", reset_token=None)


@router.post("/password/reset", response_model=ResetPasswordResponse)
async def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    redis_pool: ConnectionPool = Depends(get_redis_pool),
) -> ResetPasswordResponse:
    auth_service = AuthService(session)
    try:
        redis = Redis(connection_pool=redis_pool)
        await auth_service.reset_password(payload.token, payload.new_password, email=payload.email, redis=redis)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await publish_security_event(
        request,
        "password.reset",
        {"token_hash": hashlib.sha256(payload.token.encode()).hexdigest()},
    )
    return ResetPasswordResponse(status="ok")


@router.get("/me", response_model=UserProfileResponse)
async def get_me(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> UserProfileResponse:
    auth_service = AuthService(session)
    user = await session.get(User, principal.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user_not_found")
    email = await auth_service.get_primary_email(principal.user_id)
    return await _build_user_profile(session, user, email)


@router.get("/providers", response_model=ProvidersResponse)
async def list_providers() -> ProvidersResponse:
    return ProvidersResponse(providers=["google"])


@router.get("/sso/callback", response_model=SsoCallbackResponse)
async def sso_callback(
    request: Request,
    params: SsoCallbackQueryParams = Depends(),
    session: AsyncSession = Depends(get_db_session),
    redis_pool: ConnectionPool = Depends(get_redis_pool),
) -> SsoCallbackResponse:
    organization_id, nonce = _parse_org_and_nonce_from_state(params.state)

    # Validate nonce (one-time use, 10-minute expiry)
    redis = Redis(connection_pool=redis_pool)
    nonce_key = f"sso_nonce:{nonce}"
    stored_org_id = await redis.get(nonce_key)
    if not stored_org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired SSO state. Please try logging in again.",
        )
    if str(organization_id) != stored_org_id.decode():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SSO state mismatch",
        )
    await redis.delete(nonce_key)  # One-time use

    casdoor_service = _get_casdoor_service(request)
    auth_service = AuthService(session)
    try:
        exchange = await casdoor_service.exchange_code(params.code, params.state)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="sso_exchange_failed") from exc

    profile = exchange.get("profile", {})
    token_payload = exchange.get("token", {})

    # Only allow SSO login for existing users — no auto-creation (H8)
    email = profile.get("email")
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing_profile_data")

    # Look up existing user by SSO provider or email
    existing_sso = await session.execute(
        select(User).join(
            SsoProvider, SsoProvider.user_id == User.user_id
        ).where(
            SsoProvider.provider_uid == (profile.get("sub") or profile.get("id")),
        ),
    )
    user = existing_sso.scalar_one_or_none()

    if user is None:
        # Try finding by email in this org
        from auth_microservice.db.models.oltp import ContactInformation as CI
        existing_email = await session.execute(
            select(User)
            .join(CI, CI.user_id == User.user_id)
            .where(CI.email_id == email, User.organization_id == organization_id),
        )
        user = existing_email.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No account found for this email. Please contact your school admin to create your account first.",
        )

    provider_uid = profile.get("sub") or profile.get("id")
    email = profile.get("email")
    if not provider_uid or not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing_profile_data")

    try:
        await auth_service.upsert_sso_provider(user, provider_uid, email, token_payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    session_data = await auth_service.create_session(
        user,
        email,
        ip_address=_get_client_ip(request),
        user_agent=_get_user_agent(request),
    )
    profile_response = await _build_user_profile(session, user, email)
    tokens = _build_token_pair(session_data)
    return SsoCallbackResponse(tokens=tokens, user=profile_response)


@router.post("/sso/link", response_model=SsoLinkResponse)
async def link_sso(
    payload: SsoLinkRequest,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> SsoLinkResponse:
    casdoor_service = _get_casdoor_service(request)
    auth_service = AuthService(session)
    user = await session.get(User, principal.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user_not_found")
    try:
        exchange = await casdoor_service.exchange_code(payload.code, payload.state)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="sso_exchange_failed") from exc

    profile = exchange.get("profile", {})
    token_payload = exchange.get("token", {})
    provider_uid = profile.get("sub") or profile.get("id")
    email = profile.get("email")
    if not provider_uid or not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing_profile_data")

    try:
        await auth_service.upsert_sso_provider(user, provider_uid, email, token_payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return SsoLinkResponse()


@router.delete("/sso/link", response_model=SsoUnlinkResponse)
async def unlink_sso(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> SsoUnlinkResponse:
    auth_service = AuthService(session)
    await auth_service.unlink_sso_provider(principal.user_id, SsoProviderName.GOOGLE)
    return SsoUnlinkResponse()
