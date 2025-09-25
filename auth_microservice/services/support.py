"""Support ticket and comment helpers."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.db.models.oltp import (
    SupportPriorityEnum,
    SupportTicket,
    SupportTicketComment,
    TicketStatusEnum,
    User,
)


class SupportService:
    """Encapsulates support ticket CRUD operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_ticket(
        self,
        *,
        user_id: int,
        subject: str,
        description: str,
        priority: SupportPriorityEnum,
        status: TicketStatusEnum = TicketStatusEnum.OPEN,
    ) -> SupportTicket:
        ticket = SupportTicket(
            user_id=user_id,
            subject=subject,
            description=description,
            priority=priority,
            status=status,
        )
        self._session.add(ticket)
        await self._session.flush()
        await self._session.refresh(ticket)
        return ticket

    async def list_tickets(
        self,
        *,
        organization_id: int,
        status: TicketStatusEnum | None = None,
    ) -> list[tuple[SupportTicket, User]]:
        stmt: Select[tuple[SupportTicket, User]] = (
            select(SupportTicket, User)
            .join(User, SupportTicket.user_id == User.user_id)
            .where(User.organization_id == organization_id)
            .order_by(SupportTicket.created_at.desc())
        )
        if status is not None:
            stmt = stmt.where(SupportTicket.status == status)
        result = await self._session.execute(stmt)
        return list(result.all())

    async def get_ticket(
        self,
        ticket_id: int,
        *,
        organization_id: int,
    ) -> tuple[SupportTicket, User] | None:
        def _sync(  # type: ignore[return-type]
            sync_session,
            ticket_id: int,
            organization_id: int,
        ) -> tuple[SupportTicket, User] | None:
            stmt = (
                select(SupportTicket, User)
                .join(User, SupportTicket.user_id == User.user_id)
                .where(
                    SupportTicket.ticket_id == ticket_id,
                    User.organization_id == organization_id,
                )
            )
            result = sync_session.execute(stmt).first()
            return result

        return await self._session.run_sync(_sync, ticket_id, organization_id)

    async def update_ticket(
        self,
        ticket: SupportTicket,
        updates: dict[str, Any],
    ) -> SupportTicket:
        if "subject" in updates and updates["subject"] is not None:
            ticket.subject = updates["subject"]
        if "description" in updates and updates["description"] is not None:
            ticket.description = updates["description"]
        if "priority" in updates and updates["priority"] is not None:
            ticket.priority = updates["priority"]
        if "status" in updates and updates["status"] is not None:
            ticket.status = updates["status"]
        await self._session.flush()
        await self._session.refresh(ticket)
        return ticket

    async def create_comment(
        self,
        *,
        ticket: SupportTicket,
        user_id: int,
        comment: str,
    ) -> SupportTicketComment:
        comment_entry = SupportTicketComment(
            ticket_id=ticket.ticket_id,
            user_id=user_id,
            comment=comment,
        )
        self._session.add(comment_entry)
        await self._session.flush()
        await self._session.refresh(comment_entry)
        return comment_entry

    async def list_comments(
        self,
        ticket_id: int,
        *,
        organization_id: int,
    ) -> list[tuple[SupportTicketComment, User]]:
        stmt: Select[tuple[SupportTicketComment, User]] = (
            select(SupportTicketComment, User)
            .join(User, SupportTicketComment.user_id == User.user_id)
            .join(SupportTicket, SupportTicket.ticket_id == SupportTicketComment.ticket_id)
            .where(
                SupportTicketComment.ticket_id == ticket_id,
                User.organization_id == organization_id,
            )
            .order_by(SupportTicketComment.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.all())
