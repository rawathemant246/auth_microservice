"""Feature flag endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from redis.asyncio.connection import ConnectionPool
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.db.dependencies import get_db_session
from auth_microservice.services.feature_flags import FeatureFlagService
from auth_microservice.services.redis.dependency import get_redis_pool
from auth_microservice.web.api.dependencies import (
    AuthenticatedPrincipal,
    require_permission,
)
from auth_microservice.web.api.v1.flags.schemas import (
    FeatureFlagsResponse,
    FeatureFlagsUpdateRequest,
)

router = APIRouter(prefix="/v1/flags", tags=["flags"])


def _ensure_same_organization(principal: AuthenticatedPrincipal, organization_id: int) -> None:
    if principal.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")


@router.get("/{organization_id}", response_model=FeatureFlagsResponse)
async def get_feature_flags(
    organization_id: int,
    principal: AuthenticatedPrincipal = Depends(require_permission("settings.read")),
    _: AsyncSession = Depends(get_db_session),
    redis_pool: ConnectionPool = Depends(get_redis_pool),
) -> FeatureFlagsResponse:
    _ensure_same_organization(principal, organization_id)
    redis = Redis(connection_pool=redis_pool)
    service = FeatureFlagService(redis)
    flags = await service.get_flags(organization_id)
    return FeatureFlagsResponse(flags=flags)


@router.put("/{organization_id}", response_model=FeatureFlagsResponse)
async def update_feature_flags(
    organization_id: int,
    payload: FeatureFlagsUpdateRequest,
    principal: AuthenticatedPrincipal = Depends(require_permission("settings.update")),
    _: AsyncSession = Depends(get_db_session),
    redis_pool: ConnectionPool = Depends(get_redis_pool),
) -> FeatureFlagsResponse:
    _ensure_same_organization(principal, organization_id)
    redis = Redis(connection_pool=redis_pool)
    service = FeatureFlagService(redis)
    updated = await service.set_flags(organization_id, payload.flags)
    return FeatureFlagsResponse(flags=updated)
