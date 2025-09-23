"""Settings endpoints backed by the document store."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from auth_microservice.services.document_store import DocumentStoreService
from auth_microservice.web.api.settings.schemas import (
    OrganizationSettingsResponse,
    PrivacySettingsResponse,
    UserFeedbackResponse,
)

router = APIRouter(prefix="/settings", tags=["settings"])


def _get_document_store(request: Request) -> DocumentStoreService:
    return request.app.state.document_store


@router.get("/organization/{organization_id}", response_model=OrganizationSettingsResponse)
async def get_organization_settings(organization_id: int, request: Request) -> OrganizationSettingsResponse:
    service = _get_document_store(request)
    settings_doc = await service.get_organization_settings(organization_id)
    return OrganizationSettingsResponse(organization_id=organization_id, settings=settings_doc)


@router.get(
    "/organization/{organization_id}/privacy",
    response_model=PrivacySettingsResponse,
)
async def get_privacy_settings(organization_id: int, request: Request) -> PrivacySettingsResponse:
    service = _get_document_store(request)
    settings_doc = await service.get_privacy_settings(organization_id)
    return PrivacySettingsResponse(organization_id=organization_id, settings=settings_doc)


@router.get(
    "/organization/{organization_id}/feedback",
    response_model=UserFeedbackResponse,
)
async def get_user_feedback(
    organization_id: int,
    request: Request,
    user_id: int | None = Query(default=None, description="Optional user filter"),
) -> UserFeedbackResponse:
    service = _get_document_store(request)
    feedback = await service.get_user_feedback(organization_id, user_id)
    return UserFeedbackResponse(organization_id=organization_id, feedback=feedback)
