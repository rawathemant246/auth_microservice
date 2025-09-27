"""Search API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.db.dependencies import get_db_session
from auth_microservice.services.document_store import DocumentStoreService
from auth_microservice.services.search import SearchService
from auth_microservice.web.api.dependencies import (
    AuthenticatedPrincipal,
    require_permission,
)
from auth_microservice.web.api.v1.search.schemas import SearchResponse

search_router = APIRouter(prefix="/v1", tags=["search"])


def _document_store(request: Request) -> DocumentStoreService:
    return request.app.state.document_store


@search_router.get("/search", response_model=SearchResponse)
async def search(
    query: str,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_permission("search.read")),
    session: AsyncSession = Depends(get_db_session),
) -> SearchResponse:
    if not query:
        raise HTTPException(status_code=400, detail="query_required")
    service = SearchService(session)
    document_store = _document_store(request)
    payload = await service.search(
        organization_id=principal.organization_id,
        query=query,
        document_store=document_store,
    )
    return SearchResponse(**payload)


__all__ = ["search_router"]
