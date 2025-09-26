"""Metrics ingestion and export endpoints."""

from __future__ import annotations

import os
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, REGISTRY, generate_latest
from prometheus_client import multiprocess
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.db.dependencies import get_db_session
from auth_microservice.services.metrics import MetricsService
from auth_microservice.settings import settings
from auth_microservice.web.api.metrics.schemas import (
    SystemAlertIngestRequest,
    SystemAlertIngestResponse,
    SystemHealthIngestRequest,
    SystemHealthIngestResponse,
    UsageMetricIngestRequest,
    UsageMetricIngestResponse,
)

router = APIRouter(prefix="/metrics", tags=["metrics"])


def _validate_ingest_secret(secret_header: str | None) -> None:
    """Ensure internal ingestion endpoints are protected."""

    configured_secrets = [
        secret for secret in [settings.metrics_ingest_secret, settings.internal_api_secret] if secret
    ]
    if configured_secrets:
        for candidate in configured_secrets:
            if secret_header and secrets.compare_digest(secret_header, candidate):
                return
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_metrics_secret")

    if settings.environment not in {"dev", "pytest"}:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="metrics_ingest_not_configured")


async def require_ingest_secret(
    x_internal_secret: str | None = Header(default=None, alias="X-Internal-Secret"),
) -> None:
    _validate_ingest_secret(x_internal_secret)


def _current_registry() -> CollectorRegistry:
    """Build the correct Prometheus registry depending on workers."""

    multiproc_dir = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    if multiproc_dir:
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return registry
    return REGISTRY  # type: ignore[return-value]


@router.post(
    "/system-health",
    response_model=SystemHealthIngestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_system_health(
    payload: SystemHealthIngestRequest,
    _: None = Depends(require_ingest_secret),
    session: AsyncSession = Depends(get_db_session),
) -> SystemHealthIngestResponse:
    service = MetricsService(session)
    entry = await service.record_system_health(payload.model_dump())
    return SystemHealthIngestResponse.model_validate(entry)


@router.post(
    "/system-alerts",
    response_model=SystemAlertIngestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_system_alert(
    payload: SystemAlertIngestRequest,
    _: None = Depends(require_ingest_secret),
    session: AsyncSession = Depends(get_db_session),
) -> SystemAlertIngestResponse:
    service = MetricsService(session)
    entry = await service.record_system_alert(payload.model_dump())
    return SystemAlertIngestResponse.model_validate(entry)


@router.post(
    "/usage",
    response_model=UsageMetricIngestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_usage_metric(
    payload: UsageMetricIngestRequest,
    _: None = Depends(require_ingest_secret),
    session: AsyncSession = Depends(get_db_session),
) -> UsageMetricIngestResponse:
    service = MetricsService(session)
    entry = await service.record_usage_metric(payload.model_dump())
    return UsageMetricIngestResponse.model_validate(entry)


@router.get("/prometheus")
async def prometheus_metrics() -> Response:
    registry = _current_registry()
    metrics_payload = generate_latest(registry)
    return Response(content=metrics_payload, media_type=CONTENT_TYPE_LATEST)
