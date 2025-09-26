"""Internal maintenance endpoints."""

from __future__ import annotations

import secrets
from importlib import metadata

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.db.dependencies import get_db_session
from auth_microservice.services.search import SearchService
from auth_microservice.settings import settings

router = APIRouter(tags=["internal"])


def _validate_internal_secret(secret_header: str | None) -> None:
    configured = [secret for secret in [settings.internal_api_secret] if secret]
    if configured:
        for candidate in configured:
            if secret_header and secrets.compare_digest(secret_header, candidate):
                return
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_internal_secret")

    if settings.environment not in {"dev", "pytest"}:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="internal_access_not_configured")


async def require_internal_secret(
    x_internal_secret: str | None = Header(default=None, alias="X-Internal-Secret"),
) -> None:
    _validate_internal_secret(x_internal_secret)


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(session: AsyncSession = Depends(get_db_session)) -> dict[str, str]:
    await session.execute(select(1))
    return {"status": "ready"}


@router.get("/version")
async def version() -> dict[str, str]:
    try:
        package_version = metadata.version("auth_microservice")
    except metadata.PackageNotFoundError:
        package_version = "unknown"
    return {"version": package_version}


@router.post("/internal/reindex")
async def reindex(
    request: Request,
    _: None = Depends(require_internal_secret),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, int | str]:
    document_store = request.app.state.document_store
    search_service = SearchService(session)
    result = await search_service.rebuild_indexes(document_store=document_store)
    return {"status": "reindexed", "documents_indexed": result.get("documents_indexed", 0)}


@router.post("/internal/cache/invalidate")
async def invalidate_cache(
    request: Request,
    _: None = Depends(require_internal_secret),
) -> dict[str, str]:
    await request.app.state.rbac_service.invalidate_cache()
    return {"status": "invalidated"}
