"""Services handling metrics ingestion and persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.db.models.oltp import SystemAlert, SystemHealthLog, UsageMetric


def _ensure_aware(dt: datetime | None) -> datetime | None:
    """Normalize datetimes to UTC-aware values."""

    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class MetricsService:
    """Encapsulates ingestion logic for system metrics."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record_system_health(self, payload: dict[str, Any]) -> SystemHealthLog:
        """Persist a system health snapshot."""

        entry = SystemHealthLog(
            organization_id=payload["organization_id"],
            server_uptime=payload.get("server_uptime"),
            active_users=payload.get("active_users"),
            storage_usage=payload.get("storage_usage"),
            cpu_usage=payload.get("cpu_usage"),
            memory_usage=payload.get("memory_usage"),
            log_date=_ensure_aware(payload.get("log_date")) or datetime.now(timezone.utc),
        )
        self._session.add(entry)
        await self._session.flush()
        await self._session.refresh(entry)
        return entry

    async def record_system_alert(self, payload: dict[str, Any]) -> SystemAlert:
        """Persist a system alert entry."""

        entry = SystemAlert(
            organization_id=payload["organization_id"],
            alert_type=payload["alert_type"],
            alert_message=payload["alert_message"],
            resolved=payload.get("resolved", False),
            alert_date=_ensure_aware(payload.get("alert_date")),
        )
        self._session.add(entry)
        await self._session.flush()
        await self._session.refresh(entry)
        return entry

    async def record_usage_metric(self, payload: dict[str, Any]) -> UsageMetric:
        """Persist an organisation usage metric snapshot."""

        entry = UsageMetric(
            school_id=payload["organization_id"],
            metric_date=_ensure_aware(payload.get("metric_date")) or datetime.now(timezone.utc),
            active_users=payload.get("active_users"),
            storage_used=payload.get("storage_used"),
        )
        self._session.add(entry)
        await self._session.flush()
        await self._session.refresh(entry)
        return entry
