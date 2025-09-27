"""Versioned authentication and SSO endpoints."""

from __future__ import annotations

import hashlib
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from redis.asyncio import Redis
from redis.asyncio.connection import ConnectionPool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.db.dependencies import get_db_session
from auth_microservice.db.models.oltp import ContactInformation, SsoProviderName, User
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


def _parse_org_from_state(state: str) -> int:
    try:
        prefix, org_part, _ = state.split(":", 2)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_state") from exc
    if prefix != "org":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_state")
    try:
        return int(org_part)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_state") from exc


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
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
        await auth_service.reset_password(payload.token, payload.new_password, redis=redis)
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
) -> SsoCallbackResponse:
    organization_id = _parse_org_from_state(params.state)
    casdoor_service = _get_casdoor_service(request)
    auth_service = AuthService(session)
    try:
        exchange = await casdoor_service.exchange_code(params.code, params.state)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="sso_exchange_failed") from exc

    profile = exchange.get("profile", {})
    token_payload = exchange.get("token", {})

    try:
        user = await auth_service.get_or_create_user_from_sso(profile, organization_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

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
