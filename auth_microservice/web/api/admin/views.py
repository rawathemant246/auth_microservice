"""Admin panel endpoints for organization insights and maintenance."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.db.dependencies import get_db_session
from auth_microservice.services.admin import AdminService
from auth_microservice.settings import settings
from auth_microservice.web.api.admin.schemas import (
    BootstrapSeedResponse,
    OrganizationOverviewResponse,
    RbacSnapshotResponse,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def _validate_internal_secret(secret_header: str | None) -> None:
    configured = [secret for secret in [settings.internal_api_secret] if secret]
    if configured:
        for candidate in configured:
            if secret_header and secrets.compare_digest(secret_header, candidate):
                return
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_internal_secret")

    if settings.environment not in {"dev", "pytest"}:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="internal_access_not_configured")


async def require_internal_secret(
    x_internal_secret: str | None = Header(default=None, alias="X-Internal-Secret"),
) -> None:
    _validate_internal_secret(x_internal_secret)


@router.get("/orgs/{organization_id}/overview", response_model=OrganizationOverviewResponse)
async def get_organization_overview(
    organization_id: int,
    _: None = Depends(require_internal_secret),
    session: AsyncSession = Depends(get_db_session),
) -> OrganizationOverviewResponse:
    service = AdminService(session)
    try:
        overview = await service.get_org_overview(organization_id)
    except ValueError as exc:
        if str(exc) == "organization_not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="organization_not_found") from exc
        raise
    return OrganizationOverviewResponse.model_validate(overview)


@router.get("/rbac/snapshot/{organization_id}", response_model=RbacSnapshotResponse)
async def get_rbac_snapshot(
    organization_id: int,
    _: None = Depends(require_internal_secret),
    session: AsyncSession = Depends(get_db_session),
) -> RbacSnapshotResponse:
    service = AdminService(session)
    try:
        snapshot = await service.get_rbac_snapshot(organization_id)
    except ValueError as exc:
        if str(exc) == "organization_not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="organization_not_found") from exc
        raise
    return RbacSnapshotResponse.model_validate(snapshot)


@router.post("/bootstrap/seed", response_model=BootstrapSeedResponse, status_code=status.HTTP_202_ACCEPTED)
async def reseed_defaults(
    _: None = Depends(require_internal_secret),
    session: AsyncSession = Depends(get_db_session),
) -> BootstrapSeedResponse:
    if settings.environment.lower() in {"prod", "production"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="operation_not_allowed_in_prod")
    service = AdminService(session)
    processed = await service.reseed_defaults()
    return BootstrapSeedResponse(organizations_seeded=processed)
