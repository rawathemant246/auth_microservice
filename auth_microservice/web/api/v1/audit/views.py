"""Audit endpoints."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.db.dependencies import get_db_session
from auth_microservice.services.audit import AuditService
from auth_microservice.web.api.dependencies import AuthenticatedPrincipal, require_permission
from auth_microservice.web.api.v1.audit.schemas import AuditLogResponse, AuditLogsResponse

audit_router = APIRouter(prefix="/v1/audit", tags=["audit"])


@audit_router.get("/logs", response_model=AuditLogsResponse)
async def list_audit_logs(
    actor_user_id: int | None = Query(default=None, alias="actor"),
    table: str | None = Query(default=None),
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    principal: AuthenticatedPrincipal = Depends(require_permission("audit.log.read")),
    session: AsyncSession = Depends(get_db_session),
) -> AuditLogsResponse:
    service = AuditService(session)
    logs = await service.list_logs(
        principal.organization_id,
        actor_user_id=actor_user_id,
        table=table,
        start=start,
        end=end,
    )
    return AuditLogsResponse(items=[AuditLogResponse.model_validate(log) for log in logs])


__all__ = ["audit_router"]
