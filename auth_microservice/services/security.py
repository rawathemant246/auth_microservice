"""Security alert management helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.db.models.oltp import AlertStatusEnum, SecurityAlert, User


class SecurityService:
    """Encapsulates operations around security alerts."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_alerts(
        self,
        organization_id: int,
        *,
        status: AlertStatusEnum | None = None,
        alert_type: str | None = None,
    ) -> list[SecurityAlert]:
        stmt: Select[SecurityAlert] = (
            select(SecurityAlert)
            .join(User, SecurityAlert.user_id == User.user_id)
            .where(User.organization_id == organization_id)
            .order_by(SecurityAlert.created_at.desc())
        )
        if status is not None:
            stmt = stmt.where(SecurityAlert.alert_status == status)
        if alert_type:
            stmt = stmt.where(SecurityAlert.alert_type == alert_type)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_alert(self, alert_id: int) -> SecurityAlert | None:
        return await self._session.get(SecurityAlert, alert_id)

    async def update_alert(
        self,
        alert: SecurityAlert,
        updates: dict[str, Any],
    ) -> SecurityAlert:
        status_change = False
        if "alert_status" in updates and updates["alert_status"] is not None:
            alert.alert_status = updates["alert_status"]
            status_change = True
        if "alert_message" in updates and updates["alert_message"] is not None:
            alert.alert_message = updates["alert_message"]
        if "resolved_at" in updates:
            alert.resolved_at = updates["resolved_at"]
        elif status_change:
            if alert.alert_status == AlertStatusEnum.RESOLVED:
                alert.resolved_at = datetime.now(timezone.utc)
            else:
                alert.resolved_at = None

        await self._session.flush()
        await self._session.refresh(alert)
        return alert
