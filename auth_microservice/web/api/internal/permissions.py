"""Internal endpoint exposing a user's effective permissions to lms-backend.

lms-backend holds no authorization state of its own. It resolves a caller's
permissions here once per cache window and then authorizes locally, which keeps
this service the single source of truth while costing one hop per user per
window rather than one per request.
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.db.dependencies import get_db_session
from auth_microservice.db.models.oltp import Role, User
from auth_microservice.services.rbac_admin import RbacAdminService
from auth_microservice.settings import settings
from auth_microservice.web.api.internal.schemas import UserPermissionsResponse

router = APIRouter(prefix="/internal/v1", tags=["internal"])


async def require_internal_secret(
    x_internal_secret: str | None = Header(default=None, alias="X-Internal-Secret"),
) -> None:
    """Service-to-service guard.

    Deliberately stricter than the shared check in ``internal/views.py``, which
    falls open when no secret is configured in dev. This endpoint hands out
    authorization data, so an unset secret must fail rather than expose it.
    """
    expected = settings.internal_api_secret
    if (
        not expected
        or not x_internal_secret
        or not hmac.compare_digest(x_internal_secret, expected)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="invalid_internal_secret",
        )


@router.get(
    "/orgs/{organization_id}/users/{user_id}/permissions",
    response_model=UserPermissionsResponse,
    dependencies=[Depends(require_internal_secret)],
)
async def get_user_permissions(
    organization_id: int,
    user_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> UserPermissionsResponse:
    """Return the permission names granted to ``user_id`` within one organization.

    ``organization_id`` must match the user's own organization. The caller passes
    the org from its JWT, so checking it here means a token minted for one school
    can never resolve grants belonging to another.
    """
    user = await session.get(User, user_id)
    if user is None or user.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="user_not_found",
        )

    role_name: str | None = None
    if user.role_id is not None:
        role = await session.get(Role, user.role_id)
        if role is not None:
            role_name = role.role_name

    service = RbacAdminService(session)
    permissions = await service.get_effective_permissions(
        user_id=user.user_id,
        organization_id=organization_id,
    )

    return UserPermissionsResponse(
        user_id=user.user_id,
        organization_id=organization_id,
        role_id=user.role_id,
        role_name=role_name,
        permissions=permissions,
    )
