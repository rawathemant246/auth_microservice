"""Security alert endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.db.dependencies import get_db_session
from auth_microservice.db.models.oltp import AlertStatusEnum, User
from auth_microservice.services.security import SecurityService
from auth_microservice.web.api.dependencies import AuthenticatedPrincipal, require_permission
from auth_microservice.web.api.v1.security.schemas import (
    SecurityAlertResponse,
    SecurityAlertsResponse,
    SecurityAlertUpdateRequest,
)

security_router = APIRouter(prefix="/v1/security", tags=["security"])


@security_router.get("/alerts", response_model=SecurityAlertsResponse)
async def list_security_alerts(
    status_filter: AlertStatusEnum | None = Query(default=None, alias="status"),
    alert_type: str | None = Query(default=None),
    principal: AuthenticatedPrincipal = Depends(require_permission("security.alert.read")),
    session: AsyncSession = Depends(get_db_session),
) -> SecurityAlertsResponse:
    service = SecurityService(session)
    alerts = await service.list_alerts(
        principal.organization_id,
        status=status_filter,
        alert_type=alert_type,
    )
    return SecurityAlertsResponse(
        items=[SecurityAlertResponse.model_validate(alert) for alert in alerts],
    )


@security_router.patch("/alerts/{alert_id}", response_model=SecurityAlertResponse)
async def update_security_alert(
    alert_id: int,
    payload: SecurityAlertUpdateRequest,
    principal: AuthenticatedPrincipal = Depends(require_permission("security.alert.update")),
    session: AsyncSession = Depends(get_db_session),
) -> SecurityAlertResponse:
    service = SecurityService(session)
    alert = await service.get_alert(alert_id)
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="alert_not_found")

    user = await session.get(User, alert.user_id)
    if user is None or user.organization_id != principal.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="alert_not_found")

    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        return SecurityAlertResponse.model_validate(alert)

    alert = await service.update_alert(alert, updates)
    return SecurityAlertResponse.model_validate(alert)


__all__ = ["security_router"]
