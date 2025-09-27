"""Centralized Prometheus metrics definitions and helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from prometheus_client import Counter, Gauge
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from auth_microservice.db.models.oltp import User, UserLogin

ACTIVE_SESSIONS_GAUGE = Gauge(
    "auth_active_sessions",
    "Number of active sessions per organization.",
    labelnames=("organization_id",),
)

RBAC_CACHE_HITS = Counter(
    "auth_rbac_cache_hits_total",
    "Number of RBAC cache hits during permission evaluation.",
    labelnames=("organization_id",),
)

RBAC_CACHE_MISSES = Counter(
    "auth_rbac_cache_misses_total",
    "Number of RBAC cache misses during permission evaluation.",
    labelnames=("organization_id",),
)


async def refresh_active_sessions_gauge(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Rebuild the active sessions gauge from the database state."""

    ACTIVE_SESSIONS_GAUGE.clear()
    now = datetime.now(timezone.utc)
    async with session_factory() as session:
        result = await session.execute(
            select(User.organization_id, func.count())
            .join(UserLogin, UserLogin.user_id == User.user_id)
            .where(UserLogin.revoked_at.is_(None))
            .where(UserLogin.refresh_token_expires_at > now)
            .group_by(User.organization_id),
        )
        for organization_id, count in result.all():
            ACTIVE_SESSIONS_GAUGE.labels(organization_id=str(organization_id)).set(count)
