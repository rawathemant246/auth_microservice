"""Prometheus metrics export endpoint."""

from __future__ import annotations

import os

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, CollectorRegistry, generate_latest, multiprocess

router = APIRouter(prefix="/metrics", tags=["metrics"])


def _current_registry() -> CollectorRegistry:
    """Build the correct Prometheus registry depending on workers."""

    multiproc_dir = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    if multiproc_dir:
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return registry
    return REGISTRY  # type: ignore[return-value]


@router.get("/prometheus")
async def prometheus_metrics() -> Response:
    registry = _current_registry()
    metrics_payload = generate_latest(registry)
    return Response(content=metrics_payload, media_type=CONTENT_TYPE_LATEST)
