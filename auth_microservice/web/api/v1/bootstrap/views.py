"""Bootstrap endpoints for first-tenant provisioning."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.db.dependencies import get_db_session
from auth_microservice.services.auth.service import AuthService
from auth_microservice.services.bootstrap import PlatformBootstrapService
from auth_microservice.services.organizations import OrganizationService
from auth_microservice.settings import settings
from auth_microservice.web.api.v1.bootstrap.schemas import (
    BootstrapOrganizationRequest,
    BootstrapOrganizationResponse,
)

router = APIRouter(prefix="/v1/bootstrap", tags=["bootstrap"])

def _validate_bootstrap_secret(secret: str | None) -> None:
    if not settings.bootstrap_secret:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="bootstrap_not_configured")
    if secret is None or not secrets.compare_digest(secret, settings.bootstrap_secret):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid_bootstrap_secret")


@router.post("/organization", response_model=BootstrapOrganizationResponse, status_code=status.HTTP_201_CREATED)
async def bootstrap_organization(
    payload: BootstrapOrganizationRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    x_bootstrap_secret: str | None = Header(default=None, alias="X-Bootstrap-Secret"),
) -> BootstrapOrganizationResponse:
    """Create the initial organization and administrator guarded by a shared secret."""

    _validate_bootstrap_secret(x_bootstrap_secret)

    bootstrapper = PlatformBootstrapService(session)
    if not await bootstrapper.organizations_exist():
        result = await bootstrapper.bootstrap_superuser(payload.admin_user.model_dump())
        await request.app.state.rbac_service.reload_policies()
        return BootstrapOrganizationResponse(
            organization_id=result.organization.organization_id,
            organization_name=result.organization.organization_name,
            admin_user_id=result.user.user_id,
            admin_role_id=result.role.role_id,
        )

    organization_service = OrganizationService(session)
    try:
        organization, admin_role = await organization_service.create_organization(
            name=payload.organization_name,
            license_status=payload.license_status,
        )
    except ValueError as exc:
        if str(exc) == "organization_name_exists":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="organization_exists") from exc
        raise

    auth_service = AuthService(session)
    admin = payload.admin_user
    admin_payload: dict[str, object] = {
        "first_name": admin.first_name,
        "middle_name": admin.middle_name,
        "last_name": admin.last_name,
        "username": admin.username,
        "password": admin.password,
        "date_of_birth": admin.date_of_birth,
        "gender": admin.gender,
        "organization_id": organization.organization_id,
        "role_id": admin_role.role_id,
        "nationality": admin.nationality,
        "contact_information": admin.contact_information.model_dump(),
    }

    try:
        admin_user = await auth_service.register_user(admin_payload)
    except ValueError as exc:
        detail = str(exc)
        if detail in {"username_already_exists", "email_already_exists"}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from exc

    organization.user_id = admin_user.user_id
    await session.flush()

    await request.app.state.rbac_service.invalidate_cache()

    return BootstrapOrganizationResponse(
        organization_id=organization.organization_id,
        organization_name=organization.organization_name,
        admin_user_id=admin_user.user_id,
        admin_role_id=admin_role.role_id,
    )
