"""User administration endpoints."""

from __future__ import annotations

from typing import Iterable

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.db.dependencies import get_db_session
from auth_microservice.db.models.oltp import ContactInformation, Organization, User, UserStatusEnum
from auth_microservice.services.auth.service import AuthService
from auth_microservice.services.users import UserService
from auth_microservice.services.events import publish_audit_event
from auth_microservice.web.api.dependencies import (
    AuthenticatedPrincipal,
    require_permission,
)
from auth_microservice.web.api.v1.users.schemas import (
    UserContactResponse,
    UserContactUpdateRequest,
    UserCreateRequest,
    UserResponse,
    UserUpdateRequest,
    UsersListResponse,
)


router = APIRouter(prefix="/v1", tags=["users"])


def _ensure_same_organization(principal: AuthenticatedPrincipal, organization_id: int) -> None:
    if principal.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")


def _validate_user_access(principal: AuthenticatedPrincipal, user: User) -> None:
    if user.organization_id != principal.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")


def _serialize_contact(contact: ContactInformation | None) -> tuple[str | None, dict[str, str | None]]:
    email = contact.email_id if contact else None
    contact_payload = {
        "phone_number": contact.phone_number if contact else None,
        "emergency_number": contact.emergency_number if contact else None,
        "address": contact.address if contact else None,
        "street_address": contact.street_address if contact else None,
        "city": contact.city if contact else None,
        "state": contact.state if contact else None,
        "zip_code": contact.zip_code if contact else None,
        "country": contact.country if contact else None,
    }
    return email, contact_payload


def _serialize_user(user: User, contact: ContactInformation | None) -> UserResponse:
    email, _ = _serialize_contact(contact)
    return UserResponse(
        user_id=user.user_id,
        username=user.username,
        first_name=user.first_name,
        middle_name=user.middle_name,
        last_name=user.last_name,
        organization_id=user.organization_id,
        role_id=user.role_id,
        status=user.status,
        email=email,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.post(
    "/orgs/{organization_id}/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_user_in_organization(
    organization_id: int,
    payload: UserCreateRequest,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_permission("user.invite")),
    session: AsyncSession = Depends(get_db_session),
) -> UserResponse:
    _ensure_same_organization(principal, organization_id)

    organization = await session.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="organization_not_found")

    user_service = UserService(session)
    if payload.role_id is not None:
        try:
            await user_service.ensure_role_in_organization(organization_id, payload.role_id)
        except ValueError as exc:
            if str(exc) == "role_not_in_organization":
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="role_not_in_organization") from exc
            raise

    auth_service = AuthService(session)
    user_payload: dict[str, object] = {
        "first_name": payload.first_name,
        "middle_name": payload.middle_name,
        "last_name": payload.last_name,
        "username": payload.username,
        "password": payload.password,
        "date_of_birth": payload.date_of_birth,
        "gender": payload.gender,
        "organization_id": organization_id,
        "role_id": payload.role_id,
        "nationality": payload.nationality,
        "contact_information": payload.contact_information.model_dump(),
    }

    try:
        user = await auth_service.register_user(user_payload)
    except ValueError as exc:
        detail = str(exc)
        if detail in {"username_already_exists", "email_already_exists"}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from exc

    await request.app.state.rbac_service.invalidate_cache()
    await publish_audit_event(
        request,
        "user.created",
        {
            "actor_id": principal.user_id,
            "organization_id": organization_id,
            "user_id": user.user_id,
        },
    )

    contact = await user_service.get_contact_information(user.user_id)
    return _serialize_user(user, contact)


@router.get("/orgs/{organization_id}/users", response_model=UsersListResponse)
async def list_users_in_organization(
    organization_id: int,
    principal: AuthenticatedPrincipal = Depends(require_permission("user.read")),
    session: AsyncSession = Depends(get_db_session),
    status_filter: list[UserStatusEnum] | None = Query(default=None, alias="status"),
) -> UsersListResponse:
    _ensure_same_organization(principal, organization_id)

    user_service = UserService(session)
    statuses: Iterable[UserStatusEnum] | None = status_filter if status_filter else None
    users = await user_service.list_users(organization_id, statuses=statuses)
    return UsersListResponse(items=[_serialize_user(user, contact) for user, contact in users])


async def _get_user_and_contact(
    session: AsyncSession,
    user_id: int,
) -> tuple[User, ContactInformation | None]:
    stmt = (
        select(User, ContactInformation)
        .outerjoin(ContactInformation, ContactInformation.user_id == User.user_id)
        .where(User.user_id == user_id)
    )
    result = await session.execute(stmt)
    row = result.first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")
    return row


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    principal: AuthenticatedPrincipal = Depends(require_permission("user.read")),
    session: AsyncSession = Depends(get_db_session),
) -> UserResponse:
    user, contact = await _get_user_and_contact(session, user_id)
    _validate_user_access(principal, user)
    return _serialize_user(user, contact)


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    payload: UserUpdateRequest,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_permission("user.update")),
    session: AsyncSession = Depends(get_db_session),
) -> UserResponse:
    user, contact = await _get_user_and_contact(session, user_id)
    _validate_user_access(principal, user)

    user_service = UserService(session)
    updates = payload.model_dump(exclude_unset=True)
    try:
        user = await user_service.update_user(user, updates)
    except ValueError as exc:
        detail = str(exc)
        if detail in {"invalid_status", "role_not_in_organization"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from exc
        raise

    await request.app.state.rbac_service.invalidate_cache()
    await publish_audit_event(
        request,
        "user.updated",
        {
            "actor_id": principal.user_id,
            "user_id": user.user_id,
            "organization_id": user.organization_id,
            "fields": sorted(updates.keys()),
        },
    )
    return _serialize_user(user, contact)


@router.delete("/users/{user_id}", response_model=UserResponse)
async def deactivate_user(
    user_id: int,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_permission("user.delete")),
    session: AsyncSession = Depends(get_db_session),
) -> UserResponse:
    user, contact = await _get_user_and_contact(session, user_id)
    _validate_user_access(principal, user)

    user_service = UserService(session)
    user = await user_service.deactivate_user(user)

    await request.app.state.rbac_service.invalidate_cache()
    await publish_audit_event(
        request,
        "user.deactivated",
        {
            "actor_id": principal.user_id,
            "user_id": user.user_id,
            "organization_id": user.organization_id,
        },
    )
    return _serialize_user(user, contact)


@router.get("/users/{user_id}/contact", response_model=UserContactResponse)
async def get_user_contact(
    user_id: int,
    principal: AuthenticatedPrincipal = Depends(require_permission("user.read")),
    session: AsyncSession = Depends(get_db_session),
) -> UserContactResponse:
    user, contact = await _get_user_and_contact(session, user_id)
    _validate_user_access(principal, user)

    email, payload = _serialize_contact(contact)
    if email is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="contact_not_found")

    return UserContactResponse(email=email, **payload)


@router.patch("/users/{user_id}/contact", response_model=UserContactResponse)
async def update_user_contact(
    user_id: int,
    payload: UserContactUpdateRequest,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_permission("user.update")),
    session: AsyncSession = Depends(get_db_session),
) -> UserContactResponse:
    user, _ = await _get_user_and_contact(session, user_id)
    _validate_user_access(principal, user)

    user_service = UserService(session)
    updates = payload.model_dump(exclude_unset=True)
    try:
        contact = await user_service.upsert_contact_information(user, updates)
    except ValueError as exc:
        detail = str(exc)
        if detail in {"email_required", "email_already_exists"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from exc
        raise

    await request.app.state.rbac_service.invalidate_cache()

    email, payload_dict = _serialize_contact(contact)
    if email is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="contact_missing_email")
    return UserContactResponse(email=email, **payload_dict)
