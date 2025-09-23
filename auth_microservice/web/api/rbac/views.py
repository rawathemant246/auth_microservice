"""RBAC endpoints exposing casbin enforcement."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from auth_microservice.rbac.service import RbacService
from auth_microservice.web.api.rbac.schemas import (
    RbacCheckRequest,
    RbacCheckResponse,
    UserPermissionsResponse,
)

router = APIRouter(prefix="/rbac", tags=["rbac"])


def _get_rbac_service(request: Request) -> RbacService:
    return request.app.state.rbac_service


@router.post("/check", response_model=RbacCheckResponse)
async def check_permission(
    payload: RbacCheckRequest,
    request: Request,
) -> RbacCheckResponse:
    service = _get_rbac_service(request)
    allowed = await service.enforce(
        user_id=payload.user_id,
        permission_name=payload.permission_name,
        organization_id=payload.organization_id,
    )
    return RbacCheckResponse(allowed=allowed)


@router.get("/users/{user_id}/permissions", response_model=UserPermissionsResponse)
async def list_user_permissions(
    user_id: int,
    request: Request,
    organization_id: int = Query(..., description="Organization identifier"),
) -> UserPermissionsResponse:
    service = _get_rbac_service(request)
    permissions = await service.get_user_permissions(user_id, organization_id)
    return UserPermissionsResponse(permissions=permissions)
