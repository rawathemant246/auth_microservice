"""Activity stream helpers."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.db.models.oltp import User, UserActivityLog, UserLoginActivity


class ActivityService:
    """Provides helpers for retrieving activity records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_login_activity(
        self,
        organization_id: int,
        *,
        user_id: int | None = None,
        success: bool | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[UserLoginActivity]:
        stmt: Select[UserLoginActivity] = (
            select(UserLoginActivity)
            .join(User, UserLoginActivity.user_id == User.user_id)
            .where(User.organization_id == organization_id)
            .order_by(UserLoginActivity.login_timestamp.desc())
        )
        if user_id is not None:
            stmt = stmt.where(UserLoginActivity.user_id == user_id)
        if success is not None:
            stmt = stmt.where(UserLoginActivity.login_success == success)
        if start is not None:
            stmt = stmt.where(UserLoginActivity.login_timestamp >= start)
        if end is not None:
            stmt = stmt.where(UserLoginActivity.login_timestamp <= end)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_user_activity(
        self,
        organization_id: int,
        *,
        user_id: int | None = None,
        activity_type: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[UserActivityLog]:
        stmt: Select[UserActivityLog] = (
            select(UserActivityLog)
            .join(User, UserActivityLog.user_id == User.user_id)
            .where(User.organization_id == organization_id)
            .order_by(UserActivityLog.activity_timestamp.desc())
        )
        if user_id is not None:
            stmt = stmt.where(UserActivityLog.user_id == user_id)
        if activity_type:
            stmt = stmt.where(UserActivityLog.activity_type == activity_type)
        if start is not None:
            stmt = stmt.where(UserActivityLog.activity_timestamp >= start)
        if end is not None:
            stmt = stmt.where(UserActivityLog.activity_timestamp <= end)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
