"""Support ticket endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.db.dependencies import get_db_session
from auth_microservice.db.models.oltp import SupportTicket, SupportTicketComment, TicketStatusEnum, User
from auth_microservice.services.support import SupportService
from auth_microservice.web.api.dependencies import AuthenticatedPrincipal, require_permission
from auth_microservice.web.api.v1.support.schemas import (
    SupportTicketCommentCreateRequest,
    SupportTicketCommentResponse,
    SupportTicketCommentsListResponse,
    SupportTicketCreateRequest,
    SupportTicketResponse,
    SupportTicketUpdateRequest,
    SupportTicketsListResponse,
    SupportTicketUser,
)


support_router = APIRouter(prefix="/v1/support", tags=["support"])


def _serialize_user(user: User) -> SupportTicketUser:
    return SupportTicketUser(
        user_id=user.user_id,
        first_name=user.first_name,
        last_name=user.last_name,
    )


def _serialize_ticket(ticket: SupportTicket, user: User) -> SupportTicketResponse:
    return SupportTicketResponse(
        ticket_id=ticket.ticket_id,
        subject=ticket.subject,
        description=ticket.description,
        priority=ticket.priority,
        status=ticket.status,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        user=_serialize_user(user),
    )


def _serialize_comment(comment: SupportTicketComment, user: User) -> SupportTicketCommentResponse:
    return SupportTicketCommentResponse(
        comment_id=comment.comment_id,
        comment=comment.comment,
        created_at=comment.created_at,
        user=_serialize_user(user),
    )


def _ensure_ticket(ticket_with_user: tuple[SupportTicket, User] | None) -> tuple[SupportTicket, User]:
    if ticket_with_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ticket_not_found")
    return ticket_with_user


@support_router.post(
    "/tickets",
    response_model=SupportTicketResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_ticket(
    payload: SupportTicketCreateRequest,
    principal: AuthenticatedPrincipal = Depends(require_permission("support.ticket.create")),
    session: AsyncSession = Depends(get_db_session),
) -> SupportTicketResponse:
    service = SupportService(session)
    ticket = await service.create_ticket(
        user_id=principal.user_id,
        subject=payload.subject,
        description=payload.description,
        priority=payload.priority,
    )
    user = await session.get(User, principal.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")
    return _serialize_ticket(ticket, user)


@support_router.get("/tickets", response_model=SupportTicketsListResponse)
async def list_tickets(
    status_filter: TicketStatusEnum | None = None,
    principal: AuthenticatedPrincipal = Depends(require_permission("support.ticket.read")),
    session: AsyncSession = Depends(get_db_session),
) -> SupportTicketsListResponse:
    service = SupportService(session)
    tickets = await service.list_tickets(
        organization_id=principal.organization_id,
        status=status_filter,
    )
    return SupportTicketsListResponse(
        items=[_serialize_ticket(ticket, user) for ticket, user in tickets]
    )


@support_router.get("/tickets/{ticket_id}", response_model=SupportTicketResponse)
async def get_ticket(
    ticket_id: int,
    principal: AuthenticatedPrincipal = Depends(require_permission("support.ticket.read")),
    session: AsyncSession = Depends(get_db_session),
) -> SupportTicketResponse:
    service = SupportService(session)
    ticket, user = _ensure_ticket(
        await service.get_ticket(ticket_id, organization_id=principal.organization_id)
    )
    return _serialize_ticket(ticket, user)


@support_router.patch("/tickets/{ticket_id}", response_model=SupportTicketResponse)
async def update_ticket(
    ticket_id: int,
    payload: SupportTicketUpdateRequest,
    principal: AuthenticatedPrincipal = Depends(require_permission("support.ticket.update")),
    session: AsyncSession = Depends(get_db_session),
) -> SupportTicketResponse:
    service = SupportService(session)
    ticket, user = _ensure_ticket(
        await service.get_ticket(ticket_id, organization_id=principal.organization_id)
    )
    updates = payload.model_dump(exclude_unset=True)
    ticket = await service.update_ticket(ticket, updates)
    return _serialize_ticket(ticket, user)


@support_router.post(
    "/tickets/{ticket_id}/comments",
    response_model=SupportTicketCommentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_comment(
    ticket_id: int,
    payload: SupportTicketCommentCreateRequest,
    principal: AuthenticatedPrincipal = Depends(require_permission("support.comment")),
    session: AsyncSession = Depends(get_db_session),
) -> SupportTicketCommentResponse:
    service = SupportService(session)
    ticket, _ = _ensure_ticket(
        await service.get_ticket(ticket_id, organization_id=principal.organization_id)
    )
    comment = await service.create_comment(
        ticket=ticket,
        user_id=principal.user_id,
        comment=payload.comment,
    )
    user = await session.get(User, principal.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")
    return _serialize_comment(comment, user)


@support_router.get(
    "/tickets/{ticket_id}/comments",
    response_model=SupportTicketCommentsListResponse,
)
async def list_comments(
    ticket_id: int,
    principal: AuthenticatedPrincipal = Depends(require_permission("support.ticket.read")),
    session: AsyncSession = Depends(get_db_session),
) -> SupportTicketCommentsListResponse:
    service = SupportService(session)
    _ensure_ticket(
        await service.get_ticket(ticket_id, organization_id=principal.organization_id)
    )
    comments = await service.list_comments(ticket_id, organization_id=principal.organization_id)
    return SupportTicketCommentsListResponse(
        items=[_serialize_comment(comment, user) for comment, user in comments]
    )


__all__ = ["support_router"]
