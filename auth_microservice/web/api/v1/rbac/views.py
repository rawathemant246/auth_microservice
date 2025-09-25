"""RBAC administration endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.db.dependencies import get_db_session
from auth_microservice.db.models.oltp import Permission, Role, RolePermission, User
from auth_microservice.rbac.service import RbacService
from auth_microservice.services.rbac_admin import RbacAdminService
from auth_microservice.web.api.dependencies import AuthenticatedPrincipal, require_permission
from auth_microservice.web.api.v1.rbac.schemas import (
    EffectivePermissionsResponse,
    PermissionCreateRequest,
    PermissionResponse,
    PermissionsListResponse,
    RoleCreateRequest,
    RolePermissionAssignRequest,
    RoleResponse,
    RolesListResponse,
    RoleUpdateRequest,
    UserRoleAssignRequest,
)


router = APIRouter(prefix="/v1/rbac", tags=["rbac"])


def _serialize_role(role: Role, permission_ids: list[int]) -> RoleResponse:
    return RoleResponse(
        role_id=role.role_id,
        organization_id=role.organization_id,
        role_name=role.role_name,
        role_description=role.role_description,
        permissions=permission_ids,
        created_at=role.created_at,
        updated_at=role.updated_at,
    )


def _get_rbac_service(request: Request) -> RbacService:
    return request.app.state.rbac_service


@router.get("/roles", response_model=RolesListResponse)
async def list_roles(
    principal: AuthenticatedPrincipal = Depends(require_permission("role.read")),
    session: AsyncSession = Depends(get_db_session),
) -> RolesListResponse:
    service = RbacAdminService(session)
    items = await service.list_roles(principal.organization_id)
    return RolesListResponse(items=[_serialize_role(role, permissions) for role, permissions in items])


@router.post("/roles", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    payload: RoleCreateRequest,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_permission("role.create")),
    session: AsyncSession = Depends(get_db_session),
) -> RoleResponse:
    service = RbacAdminService(session)
    try:
        role = await service.create_role(
            principal.organization_id,
            role_name=payload.role_name,
            role_description=payload.role_description,
        )
    except ValueError as exc:
        if str(exc) == "role_name_exists":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="role_name_exists") from exc
        raise

    await _get_rbac_service(request).invalidate_cache()
    return _serialize_role(role, [])


@router.patch("/roles/{role_id}", response_model=RoleResponse)
async def update_role(
    role_id: int,
    payload: RoleUpdateRequest,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_permission("role.update")),
    session: AsyncSession = Depends(get_db_session),
) -> RoleResponse:
    role = await session.get(Role, role_id)
    if role is None or role.organization_id != principal.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="role_not_found")

    service = RbacAdminService(session)
    try:
        role = await service.update_role(
            role,
            role_name=payload.role_name,
            role_description=payload.role_description,
        )
    except ValueError as exc:
        if str(exc) == "role_name_exists":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="role_name_exists") from exc
        raise

    permission_result = await session.execute(
        select(RolePermission.permission_id)
        .where(
            RolePermission.role_id == role.role_id,
            RolePermission.organization_id == principal.organization_id,
        )
        .order_by(RolePermission.permission_id)
    )
    permissions = list(permission_result.scalars().all())
    await _get_rbac_service(request).invalidate_cache()
    return _serialize_role(role, permissions)


@router.delete(
    "/roles/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def delete_role(
    role_id: int,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_permission("role.delete")),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    role = await session.get(Role, role_id)
    if role is None or role.organization_id != principal.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="role_not_found")

    service = RbacAdminService(session)
    await service.delete_role(role)
    await _get_rbac_service(request).invalidate_cache()


@router.get("/permissions", response_model=PermissionsListResponse)
async def list_permissions(
    _: AuthenticatedPrincipal = Depends(require_permission("perm.read")),
    session: AsyncSession = Depends(get_db_session),
) -> PermissionsListResponse:
    service = RbacAdminService(session)
    items = await service.list_permissions()
    return PermissionsListResponse(items=[PermissionResponse.model_validate(item) for item in items])


@router.post("/permissions", response_model=PermissionResponse, status_code=status.HTTP_201_CREATED)
async def create_permission(
    payload: PermissionCreateRequest,
    request: Request,
    _: AuthenticatedPrincipal = Depends(require_permission("perm.create")),
    session: AsyncSession = Depends(get_db_session),
) -> PermissionResponse:
    service = RbacAdminService(session)
    try:
        permission = await service.create_permission(
            permission_name=payload.permission_name,
            permission_description=payload.permission_description,
        )
    except ValueError as exc:
        if str(exc) == "permission_name_exists":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="permission_name_exists") from exc
        raise

    await _get_rbac_service(request).invalidate_cache()
    return PermissionResponse.model_validate(permission)


@router.post(
    "/roles/{role_id}/permissions",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def assign_permission_to_role(
    role_id: int,
    payload: RolePermissionAssignRequest,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_permission("role.perm.assign")),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    role = await session.get(Role, role_id)
    if role is None or role.organization_id != principal.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="role_not_found")

    permission = await session.get(Permission, payload.permission_id)
    if permission is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="permission_not_found")

    service = RbacAdminService(session)
    try:
        await service.assign_permission_to_role(role=role, permission=permission)
    except ValueError as exc:
        if str(exc) == "role_permission_exists":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="role_permission_exists") from exc
        raise

    await _get_rbac_service(request).invalidate_cache()


@router.delete(
    "/roles/{role_id}/permissions/{permission_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def revoke_permission_from_role(
    role_id: int,
    permission_id: int,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_permission("role.perm.revoke")),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    role = await session.get(Role, role_id)
    if role is None or role.organization_id != principal.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="role_not_found")

    service = RbacAdminService(session)
    try:
        await service.revoke_permission_from_role(role=role, permission_id=permission_id)
    except ValueError as exc:
        if str(exc) == "role_permission_not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="role_permission_not_found") from exc
        raise

    await _get_rbac_service(request).invalidate_cache()


@router.post(
    "/users/{user_id}/roles",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def assign_role_to_user(
    user_id: int,
    payload: UserRoleAssignRequest,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_permission("role.assign")),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    user = await session.get(User, user_id)
    if user is None or user.organization_id != principal.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")

    role = await session.get(Role, payload.role_id)
    if role is None or role.organization_id != principal.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="role_not_found")

    service = RbacAdminService(session)
    try:
        await service.assign_role_to_user(user=user, role=role)
    except ValueError as exc:
        if str(exc) == "role_not_in_organization":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="role_not_in_organization") from exc
        raise

    await _get_rbac_service(request).invalidate_cache()


@router.delete(
    "/users/{user_id}/roles/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def revoke_role_from_user(
    user_id: int,
    role_id: int,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_permission("role.revoke")),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    user = await session.get(User, user_id)
    if user is None or user.organization_id != principal.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")

    service = RbacAdminService(session)
    try:
        await service.revoke_role_from_user(user=user, role_id=role_id)
    except ValueError as exc:
        if str(exc) == "role_not_assigned":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="role_not_assigned") from exc
        raise

    await _get_rbac_service(request).invalidate_cache()


@router.get("/effective/{user_id}", response_model=EffectivePermissionsResponse)
async def get_effective_permissions(
    user_id: int,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_permission("role.read")),
    session: AsyncSession = Depends(get_db_session),
) -> EffectivePermissionsResponse:
    user = await session.get(User, user_id)
    if user is None or user.organization_id != principal.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")

    service = RbacAdminService(session)
    permissions = await service.get_effective_permissions(
        user_id=user.user_id,
        organization_id=user.organization_id,
    )
    return EffectivePermissionsResponse(permissions=permissions)
