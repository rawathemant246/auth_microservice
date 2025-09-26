"""Cross-resource search helpers."""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_microservice.db.models.oltp import AuditLog, SupportTicket, User
from auth_microservice.services.document_store import DocumentStoreService


class SearchService:
    """Aggregate search across support tickets, feedback, and logs."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search(
        self,
        *,
        organization_id: int,
        query: str,
        document_store: DocumentStoreService,
        limit: int = 20,
    ) -> dict[str, Any]:
        tickets = await self._search_tickets(organization_id=organization_id, query=query, limit=limit)
        feedback = await document_store.search_feedback(
            organization_id=organization_id,
            query=query,
            limit=limit,
        )
        logs = await self._search_logs(organization_id=organization_id, query=query, limit=limit)
        return {
            "query": query,
            "tickets": tickets,
            "feedback": feedback,
            "logs": logs,
        }

    async def _search_tickets(
        self,
        *,
        organization_id: int,
        query: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        pattern = f"%{query}%"
        stmt = (
            select(SupportTicket, User)
            .join(User, SupportTicket.user_id == User.user_id)
            .where(User.organization_id == organization_id)
            .where(
                or_(
                    SupportTicket.subject.ilike(pattern),
                    SupportTicket.description.ilike(pattern),
                )
            )
            .order_by(SupportTicket.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        items: list[dict[str, Any]] = []
        for ticket, user in result.all():
            items.append(
                {
                    "ticket_id": ticket.ticket_id,
                    "subject": ticket.subject,
                    "status": ticket.status.value,
                    "priority": ticket.priority.value,
                    "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
                    "user": {
                        "user_id": user.user_id,
                        "first_name": user.first_name,
                        "last_name": user.last_name,
                    },
                }
            )
        return items

    async def _search_logs(
        self,
        *,
        organization_id: int,
        query: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        pattern = f"%{query}%"
        stmt = (
            select(AuditLog, User)
            .join(User, AuditLog.user_id == User.user_id)
            .where(User.organization_id == organization_id)
            .where(
                or_(
                    AuditLog.action_type.ilike(pattern),
                    AuditLog.action_description.ilike(pattern),
                )
            )
            .order_by(AuditLog.action_timestamp.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        items: list[dict[str, Any]] = []
        for log, user in result.all():
            items.append(
                {
                    "log_id": log.log_id,
                    "action_type": log.action_type,
                    "action_description": log.action_description,
                    "action_timestamp": log.action_timestamp.isoformat()
                    if log.action_timestamp
                    else None,
                    "user": {
                        "user_id": user.user_id,
                        "first_name": user.first_name,
                        "last_name": user.last_name,
                    },
                }
            )
        return items

    async def rebuild_indexes(
        self,
        *,
        document_store: DocumentStoreService,
    ) -> dict[str, int]:
        """Placeholder hook to trigger downstream index rebuilds."""

        # At present the document store does not expose specialised index rebuild
        # operations. Returning a static payload keeps the endpoint idempotent
        # while providing a future extension point.
        _ = document_store
        return {"documents_indexed": 0}
