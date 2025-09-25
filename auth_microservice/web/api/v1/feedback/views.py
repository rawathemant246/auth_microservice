"""Feedback endpoints backed by the document store."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.db.dependencies import get_db_session
from auth_microservice.services.document_store import DocumentStoreService
from auth_microservice.web.api.dependencies import AuthenticatedPrincipal, require_permission
from auth_microservice.web.api.v1.feedback.schemas import (
    FeedbackCreateRequest,
    FeedbackListResponse,
    FeedbackResponse,
    FeedbackUpdateRequest,
)


feedback_router = APIRouter(prefix="/v1", tags=["feedback"])


def _document_store(request: Request) -> DocumentStoreService:
    return request.app.state.document_store


def _normalize_feedback(doc: dict) -> FeedbackResponse:
    created_at = doc.get("created_at")
    updated_at = doc.get("updated_at")
    return FeedbackResponse(
        feedback_id=doc["feedback_id"],
        organization_id=doc["organization_id"],
        user_id=doc["user_id"],
        content=doc.get("content", ""),
        category=doc.get("category", ""),
        status=doc.get("status", ""),
        created_at=created_at,
        updated_at=updated_at,
    )


@feedback_router.post("/feedback", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
async def create_feedback(
    payload: FeedbackCreateRequest,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_permission("feedback.create")),
    session: AsyncSession = Depends(get_db_session),  # noqa: ARG001 - ensure dependency lifecycle
) -> FeedbackResponse:
    if payload.organization_id != principal.organization_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    document_store = _document_store(request)
    document = await document_store.create_feedback(
        organization_id=payload.organization_id,
        user_id=principal.user_id,
        content=payload.content,
        category=payload.category,
        status=payload.status,
    )
    return _normalize_feedback(document)


@feedback_router.get("/feedback", response_model=FeedbackListResponse)
async def list_feedback(
    request: Request,
    organization_id: int,
    status_filter: str | None = None,
    principal: AuthenticatedPrincipal = Depends(require_permission("feedback.read")),
    session: AsyncSession = Depends(get_db_session),  # noqa: ARG001
) -> FeedbackListResponse:
    if organization_id != principal.organization_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    document_store = _document_store(request)
    documents = await document_store.list_feedback(
        organization_id=organization_id,
        user_id=None,
        status=status_filter,
    )
    return FeedbackListResponse(items=[_normalize_feedback(doc) for doc in documents])


@feedback_router.patch("/feedback/{feedback_id}", response_model=FeedbackResponse)
async def update_feedback(
    feedback_id: str,
    payload: FeedbackUpdateRequest,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_permission("feedback.update")),
    session: AsyncSession = Depends(get_db_session),  # noqa: ARG001
) -> FeedbackResponse:
    document_store = _document_store(request)
    document = await document_store.update_feedback(feedback_id, payload.model_dump(exclude_unset=True))
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="feedback_not_found")
    if document["organization_id"] != principal.organization_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    return _normalize_feedback(document)


__all__ = ["feedback_router"]
