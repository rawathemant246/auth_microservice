"""Audit log query helpers."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.db.models.oltp import AuditLog, User


class AuditService:
    """Encapsulates access to audit log records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_logs(
        self,
        organization_id: int,
        *,
        actor_user_id: int | None = None,
        table: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[AuditLog]:
        stmt: Select[AuditLog] = (
            select(AuditLog)
            .join(User, AuditLog.user_id == User.user_id)
            .where(User.organization_id == organization_id)
            .order_by(AuditLog.action_timestamp.desc())
        )
        if actor_user_id is not None:
            stmt = stmt.where(AuditLog.user_id == actor_user_id)
        if table:
            stmt = stmt.where(AuditLog.affected_table == table)
        if start is not None:
            stmt = stmt.where(AuditLog.action_timestamp >= start)
        if end is not None:
            stmt = stmt.where(AuditLog.action_timestamp <= end)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
