"""Organization administration endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.db.dependencies import get_db_session
from auth_microservice.db.models.oltp import Organization
from auth_microservice.services.auth.service import AuthService
from auth_microservice.services.document_store import DocumentStoreService
from auth_microservice.services.organizations import OrganizationService
from auth_microservice.web.api.dependencies import (
    AuthenticatedPrincipal,
    require_permission,
    require_permissions,
)
from auth_microservice.web.api.v1.orgs.schemas import (
    AdminUserCreateRequest,
    AdminUserResponse,
    OrganizationCreateRequest,
    OrganizationResponse,
    OrganizationUpdateRequest,
    OrganizationSettingsUpdateRequest,
    PrivacySettingsUpdateRequest,
    OrganizationsListResponse,
)
from auth_microservice.web.api.settings.schemas import (
    OrganizationSettingsResponse,
    PrivacySettingsResponse,
)


router = APIRouter(prefix="/v1/orgs", tags=["organizations"])


def _serialize_organization(organization: Organization) -> OrganizationResponse:
    return OrganizationResponse.model_validate(organization)


def _get_document_store(request: Request) -> DocumentStoreService:
    return request.app.state.document_store


@router.post("", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
async def create_organization(
    payload: OrganizationCreateRequest,
    request: Request,
    _: AuthenticatedPrincipal = Depends(require_permission("org.create")),
    session: AsyncSession = Depends(get_db_session),
) -> OrganizationResponse:
    service = OrganizationService(session)
    try:
        organization, _ = await service.create_organization(
            name=payload.organization_name,
            license_status=payload.license_status,
        )
    except ValueError as exc:
        if str(exc) == "organization_name_exists":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="organization_exists") from exc
        raise

    await request.app.state.rbac_service.invalidate_cache()
    return _serialize_organization(organization)


@router.get("", response_model=OrganizationsListResponse)
async def list_organizations(
    _: AuthenticatedPrincipal = Depends(require_permission("org.read")),
    session: AsyncSession = Depends(get_db_session),
) -> OrganizationsListResponse:
    service = OrganizationService(session)
    organizations = await service.list_organizations()
    return OrganizationsListResponse(items=[_serialize_organization(org) for org in organizations])


@router.get("/{organization_id}", response_model=OrganizationResponse)
async def get_organization(
    organization_id: int,
    _: AuthenticatedPrincipal = Depends(require_permission("org.read")),
    session: AsyncSession = Depends(get_db_session),
) -> OrganizationResponse:
    organization = await session.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="organization_not_found")
    return _serialize_organization(organization)


@router.patch("/{organization_id}", response_model=OrganizationResponse)
async def update_organization(
    organization_id: int,
    payload: OrganizationUpdateRequest,
    request: Request,
    _: AuthenticatedPrincipal = Depends(require_permission("org.update")),
    session: AsyncSession = Depends(get_db_session),
) -> OrganizationResponse:
    organization = await session.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="organization_not_found")

    service = OrganizationService(session)
    try:
        updates = payload.model_dump(exclude_unset=True)
        organization = await service.update_organization(organization, updates)
    except ValueError as exc:
        if str(exc) == "organization_name_exists":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="organization_exists") from exc
        raise

    await request.app.state.rbac_service.invalidate_cache()
    return _serialize_organization(organization)


@router.delete("/{organization_id}", response_model=OrganizationResponse)
async def deactivate_organization(
    organization_id: int,
    request: Request,
    _: AuthenticatedPrincipal = Depends(require_permission("org.delete")),
    session: AsyncSession = Depends(get_db_session),
) -> OrganizationResponse:
    organization = await session.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="organization_not_found")

    service = OrganizationService(session)
    organization = await service.deactivate_organization(organization)

    await request.app.state.rbac_service.invalidate_cache()
    return _serialize_organization(organization)


@router.post("/{organization_id}/admins", response_model=AdminUserResponse, status_code=status.HTTP_201_CREATED)
async def create_org_admin(
    organization_id: int,
    payload: AdminUserCreateRequest,
    request: Request,
    _: AuthenticatedPrincipal = Depends(require_permissions("user.invite", "role.assign")),
    session: AsyncSession = Depends(get_db_session),
) -> AdminUserResponse:
    organization = await session.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="organization_not_found")

    service = OrganizationService(session)
    admin_role = await service.ensure_admin_role(organization)

    auth_service = AuthService(session)
    body = payload
    user_payload: dict[str, object] = {
        "first_name": body.first_name,
        "middle_name": body.middle_name,
        "last_name": body.last_name,
        "username": body.username,
        "password": body.password,
        "date_of_birth": body.date_of_birth,
        "gender": body.gender,
        "organization_id": organization.organization_id,
        "role_id": admin_role.role_id,
        "nationality": body.nationality,
        "contact_information": body.contact_information.model_dump(),
    }

    try:
        admin_user = await auth_service.register_user(user_payload)
    except ValueError as exc:
        detail = str(exc)
        if detail in {"username_already_exists", "email_already_exists"}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from exc

    if organization.user_id is None:
        organization.user_id = admin_user.user_id

    await session.flush()
    await request.app.state.rbac_service.invalidate_cache()

    email = body.contact_information.email
    return AdminUserResponse(
        user_id=admin_user.user_id,
        username=admin_user.username,
        email=email,
        first_name=admin_user.first_name,
        last_name=admin_user.last_name,
        organization_id=admin_user.organization_id,
        role_id=admin_role.role_id,
    )


@router.get("/{organization_id}/settings", response_model=OrganizationSettingsResponse)
async def get_organization_settings(
    organization_id: int,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_permission("settings.read")),
) -> OrganizationSettingsResponse:
    _ensure_same_organization(principal, organization_id)
    document_store = _get_document_store(request)
    settings_document = await document_store.get_organization_settings(organization_id)
    return OrganizationSettingsResponse(organization_id=organization_id, settings=settings_document)


@router.put("/{organization_id}/settings", response_model=OrganizationSettingsResponse)
async def upsert_organization_settings(
    organization_id: int,
    payload: OrganizationSettingsUpdateRequest,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_permission("settings.update")),
) -> OrganizationSettingsResponse:
    _ensure_same_organization(principal, organization_id)
    document_store = _get_document_store(request)
    settings_document = await document_store.upsert_organization_settings(
        organization_id,
        payload.settings,
    )
    return OrganizationSettingsResponse(organization_id=organization_id, settings=settings_document)


@router.get("/{organization_id}/privacy", response_model=PrivacySettingsResponse)
async def get_privacy_settings(
    organization_id: int,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_permission("privacy.read")),
) -> PrivacySettingsResponse:
    _ensure_same_organization(principal, organization_id)
    document_store = _get_document_store(request)
    privacy_document = await document_store.get_privacy_settings(organization_id)
    return PrivacySettingsResponse(organization_id=organization_id, settings=privacy_document)


@router.put("/{organization_id}/privacy", response_model=PrivacySettingsResponse)
async def upsert_privacy_settings(
    organization_id: int,
    payload: PrivacySettingsUpdateRequest,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_permission("privacy.update")),
) -> PrivacySettingsResponse:
    _ensure_same_organization(principal, organization_id)
    document_store = _get_document_store(request)
    privacy_document = await document_store.upsert_privacy_settings(
        organization_id,
        payload.settings,
    )
    return PrivacySettingsResponse(organization_id=organization_id, settings=privacy_document)
