"""Activity endpoints."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.db.dependencies import get_db_session
from auth_microservice.services.activity import ActivityService
from auth_microservice.web.api.dependencies import AuthenticatedPrincipal, require_permission
from auth_microservice.web.api.v1.activity.schemas import (
    LoginActivitiesResponse,
    LoginActivityResponse,
    UserActivitiesResponse,
    UserActivityResponse,
)

activity_router = APIRouter(prefix="/v1/activity", tags=["activity"])


@activity_router.get("/logins", response_model=LoginActivitiesResponse)
async def list_login_activity(
    user_id: int | None = Query(default=None),
    success: bool | None = Query(default=None),
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    principal: AuthenticatedPrincipal = Depends(require_permission("activity.login.read")),
    session: AsyncSession = Depends(get_db_session),
) -> LoginActivitiesResponse:
    service = ActivityService(session)
    activities = await service.list_login_activity(
        principal.organization_id,
        user_id=user_id,
        success=success,
        start=start,
        end=end,
    )
    return LoginActivitiesResponse(
        items=[LoginActivityResponse.model_validate(activity) for activity in activities],
    )


@activity_router.get("/users", response_model=UserActivitiesResponse)
async def list_user_activity(
    user_id: int | None = Query(default=None),
    activity_type: str | None = Query(default=None),
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    principal: AuthenticatedPrincipal = Depends(require_permission("activity.user.read")),
    session: AsyncSession = Depends(get_db_session),
) -> UserActivitiesResponse:
    service = ActivityService(session)
    activities = await service.list_user_activity(
        principal.organization_id,
        user_id=user_id,
        activity_type=activity_type,
        start=start,
        end=end,
    )
    return UserActivitiesResponse(
        items=[UserActivityResponse.model_validate(activity) for activity in activities],
    )


__all__ = ["activity_router"]
