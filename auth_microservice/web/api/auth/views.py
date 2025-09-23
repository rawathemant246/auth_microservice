"""REST endpoints for authentication and SSO flows."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import HttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.db.dependencies import get_db_session
from auth_microservice.db.models.oltp import ContactInformation, User
from auth_microservice.rbac.service import RbacService
from auth_microservice.services.auth.service import AuthService
from auth_microservice.services.sso import CasdoorService
from auth_microservice.web.api.auth.schemas import (
    GoogleSsoCallbackRequest,
    GoogleSsoCallbackResponse,
    GoogleSsoLoginResponse,
    TokenResponse,
    UserLoginRequest,
    UserRegistrationRequest,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _build_user_response(user: User, email: str | None) -> UserResponse:
    return UserResponse(
        user_id=user.user_id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        organization_id=user.organization_id,
        role_id=user.role_id,
        email=email or "",
    )


def _get_rbac_service(request: Request) -> RbacService:
    rbac_service: RbacService = request.app.state.rbac_service
    return rbac_service


def _get_casdoor_service(request: Request) -> CasdoorService:
    casdoor_service: CasdoorService = request.app.state.casdoor_service
    return casdoor_service


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    payload: UserRegistrationRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> UserResponse:
    service = AuthService(session)
    payload_data = payload.model_dump()
    try:
        user = await service.register_user(payload_data)
    except ValueError as exc:
        detail = str(exc)
        if detail == "username_already_exists":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from exc
        if detail == "email_already_exists":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from exc

    contact_email = payload.contact_information.email
    await _get_rbac_service(request).invalidate_cache()
    return _build_user_response(user, contact_email)


@router.post("/login", response_model=TokenResponse)
async def login_user(
    payload: UserLoginRequest,
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    service = AuthService(session)
    try:
        user, email = await service.authenticate_user(payload.username, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    token, expires = await service.issue_token(user, email)
    return TokenResponse(access_token=token, expires_in=expires * 60)


@router.get("/sso/google/login", response_model=GoogleSsoLoginResponse)
async def google_sso_login(
    request: Request,
    organization_id: int = Query(..., description="Organization requesting login"),
    redirect_uri: HttpUrl = Query(..., description="Frontend redirect URI"),
) -> GoogleSsoLoginResponse:
    casdoor_service = _get_casdoor_service(request)
    nonce = secrets.token_urlsafe(16)
    state = f"org:{organization_id}:{nonce}"
    login_url = casdoor_service.get_login_url(str(redirect_uri), state)
    return GoogleSsoLoginResponse(login_url=login_url, state=state)


def _extract_org_from_state(state: str) -> int:
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


@router.post("/sso/google/callback", response_model=GoogleSsoCallbackResponse)
async def google_sso_callback(
    payload: GoogleSsoCallbackRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> GoogleSsoCallbackResponse:
    organization_id = _extract_org_from_state(payload.state)
    casdoor_service = _get_casdoor_service(request)
    auth_service = AuthService(session)
    try:
        exchange = await casdoor_service.exchange_code(payload.code, payload.state)
    except Exception as exc:  # noqa: BLE001 - bubble up as HTTP error
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="sso_exchange_failed") from exc

    profile = exchange.get("profile", {})
    token_payload = exchange.get("token", {})

    try:
        user = await auth_service.get_or_create_user_from_sso(profile, organization_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    provider_uid = profile.get("sub") or profile.get("id")
    email = profile.get("email")
    if provider_uid is None or email is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing_profile_data")

    await auth_service.upsert_sso_provider(user, provider_uid, email, token_payload)
    await _get_rbac_service(request).invalidate_cache()

    # Fetch email from contact information to ensure we have stored reference
    result = await session.execute(
        select(ContactInformation.email_id).where(ContactInformation.user_id == user.user_id)
    )
    contact_email = result.scalar_one_or_none() or email

    token, expires = await auth_service.issue_token(user, contact_email)
    user_response = _build_user_response(user, contact_email)
    return GoogleSsoCallbackResponse(
        token=TokenResponse(access_token=token, expires_in=expires * 60),
        user=user_response,
    )
